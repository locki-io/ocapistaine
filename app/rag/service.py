"""
RAG Service — orchestrates retrieval and LLM synthesis with Opik tracing.
"""

import uuid

from app.providers.base import Message
from app.providers.failover import ProviderWithFailover
from app.agents.tracing import get_tracer

from . import retrieval
from .prompts import (
    SYSTEM_PROMPT,
    RAG_USER_TEMPLATE,
    COMPARE_SYSTEM_PROMPT,
    COMPARE_USER_TEMPLATE,
)
from .store import collection_stats


class RAGService:
    """Main RAG service for OCapistaine."""

    def __init__(self, primary_provider: str = "ollama"):
        self.provider = ProviderWithFailover(primary=primary_provider)
        self.tracer = get_tracer()

    async def query(
        self,
        question: str,
        n_results: int = 5,
        filters: dict | None = None,
        thread_id: str | None = None,
    ) -> dict:
        """
        Answer a question using RAG retrieval + LLM synthesis.

        Args:
            question: User question
            n_results: Number of chunks to retrieve
            filters: Optional metadata filters (e.g. {"list_name": "audierne2026"})
            thread_id: Conversation thread ID for Opik grouping

        Returns:
            {response, sources, model, confidence, trace_id, thread_id}
        """
        thread_id = thread_id or str(uuid.uuid4())

        trace_input = {
            "question": question,
            "n_results": n_results,
            "filters": filters,
            "thread_id": thread_id,
        }

        with self.tracer.start_trace(
            name="rag_query",
            input=trace_input,
            metadata={"thread_id": thread_id, "type": "rag_query"},
            tags=["rag", "chat"],
        ) as trace:

            # === Span: Retrieval ===
            with self.tracer.span(
                name="rag_retrieval",
                input={"query": question, "n_results": n_results, "filters": filters},
                span_type="tool",
            ) as retrieval_span:
                results = retrieval.search(question, n_results=n_results, where=filters)

                retrieval_output = {
                    "chunks_found": len(results),
                    "distances": [round(r.distance, 3) for r in results],
                    "doc_ids": [r.metadata.get("doc_id", "") for r in results],
                }
                retrieval_span.update(output=retrieval_output)

            if not results:
                empty_result = {
                    "response": "Aucun document pertinent trouvé dans la base. Avez-vous ingéré les documents ?",
                    "sources": [],
                    "model": "none",
                    "confidence": 0.0,
                    "thread_id": thread_id,
                    "trace_id": trace.id if trace else None,
                }
                if trace:
                    trace.update(output=empty_result)
                return empty_result

            # Build context
            context_parts = []
            for r in results:
                source_label = r.metadata.get("title") or r.metadata.get("doc_id", "")
                cat = r.metadata.get("category", "")
                header = f"[{source_label}]" + (f" ({cat})" if cat else "")
                context_parts.append(f"{header}\n{r.content}")

            context = "\n---\n".join(context_parts)

            # === Span: LLM Synthesis ===
            messages = [
                Message("system", SYSTEM_PROMPT),
                Message("user", RAG_USER_TEMPLATE.format(context=context, question=question)),
            ]

            with self.tracer.span(
                name="rag_synthesis",
                input={
                    "question": question,
                    "context_chunks": len(results),
                    "context_chars": len(context),
                },
                span_type="llm",
            ) as synthesis_span:
                response = await self.provider.complete(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=1500,
                )

                synthesis_span.update(output={
                    "response_length": len(response.content),
                    "model": response.model,
                    "usage": response.usage,
                })

            # Deduplicate sources by doc_id
            seen = set()
            sources = []
            for r in results:
                doc_id = r.metadata.get("doc_id", "")
                if doc_id not in seen:
                    seen.add(doc_id)
                    sources.append({
                        "doc_id": doc_id,
                        "title": r.metadata.get("title", ""),
                        "category": r.metadata.get("category", ""),
                        "url": r.metadata.get("url", ""),
                        "list_name": r.metadata.get("list_name", ""),
                        "distance": r.distance,
                    })

            best_distance = min(r.distance for r in results)
            confidence = max(0.0, 1.0 - best_distance)

            result = {
                "response": response.content,
                "sources": sources,
                "model": f"{self.provider.name}/{self.provider.model}",
                "confidence": round(confidence, 3),
                "thread_id": thread_id,
                "trace_id": trace.id if trace else None,
            }

            # Update trace with final output
            if trace:
                trace.update(output={
                    "response": response.content[:500],
                    "confidence": result["confidence"],
                    "model": result["model"],
                    "sources_count": len(sources),
                })

            return result

    async def compare(
        self,
        question: str,
        list_names: list[str],
        n_per_list: int = 3,
        thread_id: str | None = None,
    ) -> dict:
        """
        Compare electoral programs across lists on a given topic.
        """
        thread_id = thread_id or str(uuid.uuid4())

        trace_input = {
            "question": question,
            "list_names": list_names,
            "n_per_list": n_per_list,
            "thread_id": thread_id,
        }

        with self.tracer.start_trace(
            name="rag_compare",
            input=trace_input,
            metadata={"thread_id": thread_id, "type": "rag_compare"},
            tags=["rag", "compare"],
        ) as trace:

            # === Span: Multi-list Retrieval ===
            with self.tracer.span(
                name="rag_compare_retrieval",
                input={"query": question, "lists": list_names, "n_per_list": n_per_list},
                span_type="tool",
            ) as retrieval_span:
                results_by_list = retrieval.search_compare(question, list_names, n_per_list)

                retrieval_output = {
                    k: len(v) for k, v in results_by_list.items()
                }
                retrieval_span.update(output={"chunks_per_list": retrieval_output})

            # Build context per list
            list_contexts_parts = []
            all_sources = []
            for name, results in results_by_list.items():
                if results:
                    excerpts = "\n".join(r.content for r in results)
                    list_contexts_parts.append(f"### {name}\n{excerpts}")
                    for r in results:
                        all_sources.append({
                            "doc_id": r.metadata.get("doc_id", ""),
                            "title": r.metadata.get("title", ""),
                            "list_name": name,
                            "distance": r.distance,
                        })
                else:
                    list_contexts_parts.append(f"### {name}\n(Aucun document trouvé)")

            list_contexts = "\n\n".join(list_contexts_parts)

            messages = [
                Message("system", COMPARE_SYSTEM_PROMPT),
                Message("user", COMPARE_USER_TEMPLATE.format(
                    list_contexts=list_contexts, question=question
                )),
            ]

            # === Span: LLM Comparison Synthesis ===
            with self.tracer.span(
                name="rag_compare_synthesis",
                input={
                    "question": question,
                    "lists": list_names,
                    "context_chars": len(list_contexts),
                },
                span_type="llm",
            ) as synthesis_span:
                response = await self.provider.complete(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=2000,
                )

                synthesis_span.update(output={
                    "response_length": len(response.content),
                    "model": response.model,
                    "usage": response.usage,
                })

            result = {
                "response": response.content,
                "lists_compared": list_names,
                "sources": all_sources,
                "model": f"{self.provider.name}/{self.provider.model}",
                "thread_id": thread_id,
                "trace_id": trace.id if trace else None,
            }

            if trace:
                trace.update(output={
                    "response": response.content[:500],
                    "model": result["model"],
                    "lists_compared": list_names,
                    "sources_count": len(all_sources),
                })

            return result

    @staticmethod
    def stats() -> dict:
        """Get RAG collection statistics."""
        return collection_stats()
