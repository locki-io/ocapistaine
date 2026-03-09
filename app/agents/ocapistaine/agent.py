"""
OCapistaine Agent — RAG-powered civic assistant.

Orchestrates chat and compare features with Opik tracing.
Follows the Forseti agent pattern: BaseAgent + AgentFeature composition.
"""

import uuid
from typing import AsyncIterator

from app.agents.base import BaseAgent
from app.agents.tracing import get_tracer, AgentTracer
from app.providers import LLMProvider
from app.providers.failover import ProviderWithFailover
from app.services.logging import AgentLogger

from .features import RAGChatFeature, RAGCompareFeature, QueryRefiner
from .features.refine import RefineResult
from .models import ChatResult, CompareResult
from .prompts import PERSONA_PROMPT


class OCapistaineAgent(BaseAgent):
    """
    RAG-powered civic assistant for Audierne-Esquibien.

    Features:
        - rag_chat: Citizen Q&A with retrieval + synthesis
        - rag_compare: Cross-list program comparison

    Usage:
        agent = OCapistaineAgent(provider_name="gemini")
        result = await agent.chat("Que proposent les listes sur l'école ?")
        result = await agent.compare("économie locale", ["paa", "spae", "ca"])
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        provider_name: str | None = None,
        model_override: str | None = None,
        tracer: AgentTracer | None = None,
    ):
        # Use ProviderWithFailover for resilience
        if provider is None:
            primary = provider_name or "ollama"
            overrides = {primary: model_override} if model_override else {}
            provider = ProviderWithFailover(primary=primary, model_overrides=overrides)

        super().__init__(provider=provider)

        # Register features
        self.register_feature(RAGChatFeature())
        self.register_feature(RAGCompareFeature())

        # Query refinement (cheap OpenAI pre-processing)
        self._refiner = QueryRefiner()

        # Tracing and logging
        self._tracer = tracer or get_tracer()
        self._logger = AgentLogger("ocapistaine")

    @property
    def persona_prompt(self) -> str:
        return PERSONA_PROMPT

    def _get_provider_info(self) -> dict:
        """Get actual provider metadata from the underlying provider (post-execution)."""
        if isinstance(self._provider, ProviderWithFailover):
            return self._provider.get_provider_info()
        # Plain provider — no failover info
        return {
            "provider": self._provider.name,
            "model_key": self._provider.model,
            "model_id": self._provider.model,
        }

    async def chat(
        self,
        question: str,
        n_results: int = 10,
        filters: dict | None = None,
        thread_id: str | None = None,
        history: list[dict] | None = None,
    ) -> ChatResult:
        """
        Citizen Q&A — retrieve and synthesize an answer.

        Args:
            question: User question in French
            n_results: Number of chunks to retrieve
            filters: Optional metadata filters
            thread_id: Conversation thread ID for Opik grouping
            history: Conversation history for follow-up context

        Returns:
            ChatResult with response, sources, confidence, trace_id
        """
        thread_id = thread_id or str(uuid.uuid4())

        # Refine + correct wording before retrieval
        refine_result = await self._refiner.refine(question, history)

        # Execute feature with refined query
        result: ChatResult = await self.execute_feature(
            "rag_chat",
            question=refine_result.query,
            n_results=n_results,
            filters=filters,
            history=history,
        )

        result.thread_id = thread_id

        # Skip tracing on errors (Forseti pattern)
        if result.confidence == 0.0:
            self._logger.warning(
                "CHAT_SKIPPED_TRACE",
                reason="no_results_or_error",
                question=question[:100],
            )
            return result

        # Trace successful query — thread groups all traces from this session
        trace_type = "rag_overview" if result.is_overview else "rag_chat"
        prov_info = self._get_provider_info()

        with self._tracer.start_thread(thread_id):
            with self._tracer.start_trace(
                name=trace_type,
                input={"question": question, "refined_query": refine_result.query},
                metadata={"agent": "ocapistaine", "feature": trace_type, "type": trace_type},
                tags=["rag", "chat", "ocapistaine"],
                provider_info=prov_info,
            ) as trace:

                # Wording + Refine spans
                self._trace_preprocess_spans(refine_result, prov_info)

                # Retrieval span — with full metrics
                self._trace_retrieval_span(
                    question=refine_result.query,
                    result_sources=result.sources,
                    metrics=result.retrieval_metrics,
                    prov_info=prov_info,
                    extra_input={"is_overview": result.is_overview},
                )

                with self._tracer.span(
                    name="rag_synthesis",
                    input={"question": refine_result.query, "context_sources": len(result.sources)},
                    span_type="llm",
                    provider_info=prov_info,
                ) as synthesis_span:
                    synthesis_span.update(output={
                        "response_length": len(result.response),
                        "model": result.model,
                        "confidence": result.confidence,
                    })
                    if hasattr(synthesis_span, "id") and synthesis_span.id:
                        self._tracer.log_span_feedback(
                            span_id=synthesis_span.id,
                            score=result.confidence,
                            feedback_type="ocapistaine.correctness",
                            comment=f"chat confidence={result.confidence:.2f}",
                        )

                if trace and hasattr(trace, "id") and trace.id:
                    result.trace_id = trace.id
                    trace.update(output={
                        "response": result.response,
                        "confidence": result.confidence,
                        "model": result.model,
                        "sources_count": len(result.sources),
                    })
                    self._tracer.log_feedback(
                        trace_id=trace.id,
                        score=result.confidence,
                        feedback_type="ocapistaine.rag_confidence",
                        comment=f"chat {len(result.sources)} sources",
                    )

        return result

    async def compare(
        self,
        question: str,
        list_names: list[str],
        n_per_list: int = 3,
        thread_id: str | None = None,
        history: list[dict] | None = None,
    ) -> CompareResult:
        """
        Compare electoral programs across lists.

        Args:
            question: Comparison topic
            list_names: Lists to compare
            n_per_list: Chunks per list
            thread_id: Conversation thread ID for Opik grouping
            history: Conversation history for follow-up context

        Returns:
            CompareResult with response, sources, trace_id
        """
        thread_id = thread_id or str(uuid.uuid4())

        # Refine + correct wording before retrieval
        refine_result = await self._refiner.refine(question, history)

        # Execute feature with refined query
        result: CompareResult = await self.execute_feature(
            "rag_compare",
            question=refine_result.query,
            list_names=list_names,
            n_per_list=n_per_list,
            history=history,
        )

        result.thread_id = thread_id

        # Skip tracing on errors
        if result.confidence == 0.0:
            self._logger.warning(
                "COMPARE_SKIPPED_TRACE",
                reason="error",
                question=question[:100],
                lists=list_names,
            )
            return result

        # Trace comparison — thread groups all traces from this session
        prov_info = self._get_provider_info()

        with self._tracer.start_thread(thread_id):
            with self._tracer.start_trace(
                name="rag_compare",
                input={"question": question, "refined_query": refine_result.query, "list_names": list_names},
                metadata={"agent": "ocapistaine", "feature": "rag_compare", "type": "rag_compare"},
                tags=["rag", "compare", "ocapistaine"],
                provider_info=prov_info,
            ) as trace:

                # Wording + Refine spans
                self._trace_preprocess_spans(refine_result, prov_info)

                # Retrieval span — with full metrics
                self._trace_retrieval_span(
                    question=refine_result.query,
                    result_sources=result.sources,
                    metrics=result.retrieval_metrics,
                    prov_info=prov_info,
                    span_name="rag_compare_retrieval",
                    extra_input={"lists": list_names},
                )

                with self._tracer.span(
                    name="rag_compare_synthesis",
                    input={"question": refine_result.query, "lists": list_names},
                    span_type="llm",
                    provider_info=prov_info,
                ) as synthesis_span:
                    synthesis_span.update(output={
                        "response_length": len(result.response),
                        "model": result.model,
                    })
                    if hasattr(synthesis_span, "id") and synthesis_span.id:
                        self._tracer.log_span_feedback(
                            span_id=synthesis_span.id,
                            score=result.confidence,
                            feedback_type="ocapistaine.correctness",
                            comment=f"compare {len(list_names)} lists",
                        )

                if trace and hasattr(trace, "id") and trace.id:
                    result.trace_id = trace.id
                    trace.update(output={
                        "response": result.response,
                        "model": result.model,
                        "lists_compared": result.lists_compared,
                        "sources_count": len(result.sources),
                    })
                    self._tracer.log_feedback(
                        trace_id=trace.id,
                        score=result.confidence,
                        feedback_type="ocapistaine.rag_confidence",
                        comment=f"compare {list_names}",
                    )

        return result

    # ── Streaming methods ──────────────────────────────────

    async def stream_chat(
        self,
        question: str,
        n_results: int = 10,
        filters: dict | None = None,
        thread_id: str | None = None,
        history: list[dict] | None = None,
    ) -> AsyncIterator[str | ChatResult]:
        """
        Stream citizen Q&A — yields text chunks, then a final ChatResult.

        The ChatResult is yielded last and contains sources, confidence,
        trace_id, etc. Use isinstance() to distinguish chunks from result.
        """
        thread_id = thread_id or str(uuid.uuid4())

        # Refine + correct wording before retrieval
        refine_result = await self._refiner.refine(question, history)

        feature: RAGChatFeature = self._features["rag_chat"]

        result = None
        async for item in feature.stream_execute(
            provider=self._provider,
            system_prompt=self.persona_prompt,
            question=refine_result.query,
            n_results=n_results,
            filters=filters,
            history=history,
        ):
            if isinstance(item, ChatResult):
                result = item
            else:
                yield item

        if result is None:
            return

        result.thread_id = thread_id

        # Trace after stream completes
        if result.confidence > 0.0:
            self._trace_chat(result, question, n_results, filters, thread_id, refine_result)

        yield result

    async def stream_compare(
        self,
        question: str,
        list_names: list[str],
        n_per_list: int = 3,
        thread_id: str | None = None,
        history: list[dict] | None = None,
    ) -> AsyncIterator[str | CompareResult]:
        """
        Stream program comparison — yields text chunks, then a final CompareResult.
        """
        thread_id = thread_id or str(uuid.uuid4())

        # Refine + correct wording before retrieval
        refine_result = await self._refiner.refine(question, history)

        feature: RAGCompareFeature = self._features["rag_compare"]

        result = None
        async for item in feature.stream_execute(
            provider=self._provider,
            system_prompt=self.persona_prompt,
            question=refine_result.query,
            list_names=list_names,
            n_per_list=n_per_list,
            history=history,
        ):
            if isinstance(item, CompareResult):
                result = item
            else:
                yield item

        if result is None:
            return

        result.thread_id = thread_id

        # Trace after stream completes
        if result.confidence > 0.0:
            self._trace_compare(result, question, list_names, n_per_list, thread_id, refine_result)

        yield result

    # ── Private tracing helpers ────────────────────────────

    def _trace_chat(
        self,
        result: ChatResult,
        question: str,
        n_results: int,
        filters: dict | None,
        thread_id: str,
        refine_result: RefineResult | None = None,
    ) -> None:
        """Trace a completed chat result to Opik (within a thread)."""
        trace_type = "rag_overview" if result.is_overview else "rag_chat"
        prov_info = self._get_provider_info()
        refined = refine_result.query if refine_result else question

        with self._tracer.start_thread(thread_id):
            with self._tracer.start_trace(
                name=trace_type,
                input={"question": question, "refined_query": refined},
                metadata={"agent": "ocapistaine", "feature": trace_type, "type": trace_type},
                tags=["rag", "chat", "ocapistaine"],
                provider_info=prov_info,
            ) as trace:
                # Wording + Refine spans
                if refine_result:
                    self._trace_preprocess_spans(refine_result, prov_info)

                self._trace_retrieval_span(
                    question=question,
                    result_sources=result.sources,
                    metrics=result.retrieval_metrics,
                    prov_info=prov_info,
                    extra_input={"is_overview": result.is_overview},
                )

                with self._tracer.span(
                    name="rag_synthesis",
                    input={"question": question, "context_sources": len(result.sources)},
                    span_type="llm",
                    provider_info=prov_info,
                ) as synthesis_span:
                    synthesis_span.update(output={
                        "response_length": len(result.response),
                        "model": result.model,
                        "confidence": result.confidence,
                    })
                    if hasattr(synthesis_span, "id") and synthesis_span.id:
                        self._tracer.log_span_feedback(
                            span_id=synthesis_span.id,
                            score=result.confidence,
                            feedback_type="ocapistaine.correctness",
                            comment=f"chat confidence={result.confidence:.2f}",
                        )

                if trace and hasattr(trace, "id") and trace.id:
                    result.trace_id = trace.id
                    trace.update(output={
                        "response": result.response,
                        "confidence": result.confidence,
                        "model": result.model,
                        "sources_count": len(result.sources),
                    })
                    self._tracer.log_feedback(
                        trace_id=trace.id,
                        score=result.confidence,
                        feedback_type="ocapistaine.rag_confidence",
                        comment=f"chat {len(result.sources)} sources",
                    )

    def _trace_compare(
        self,
        result: CompareResult,
        question: str,
        list_names: list[str],
        n_per_list: int,
        thread_id: str,
        refine_result: RefineResult | None = None,
    ) -> None:
        """Trace a completed compare result to Opik (within a thread)."""
        prov_info = self._get_provider_info()
        refined = refine_result.query if refine_result else question

        with self._tracer.start_thread(thread_id):
            with self._tracer.start_trace(
                name="rag_compare",
                input={"question": question, "refined_query": refined, "list_names": list_names},
                metadata={"agent": "ocapistaine", "feature": "rag_compare", "type": "rag_compare"},
                tags=["rag", "compare", "ocapistaine"],
                provider_info=prov_info,
            ) as trace:
                # Wording + Refine spans
                if refine_result:
                    self._trace_preprocess_spans(refine_result, prov_info)

                self._trace_retrieval_span(
                    question=question,
                    result_sources=result.sources,
                    metrics=result.retrieval_metrics,
                    prov_info=prov_info,
                    span_name="rag_compare_retrieval",
                    extra_input={"lists": list_names},
                )

                with self._tracer.span(
                    name="rag_compare_synthesis",
                    input={"question": question, "lists": list_names},
                    span_type="llm",
                    provider_info=prov_info,
                ) as synthesis_span:
                    synthesis_span.update(output={
                        "response_length": len(result.response),
                        "model": result.model,
                    })
                    if hasattr(synthesis_span, "id") and synthesis_span.id:
                        self._tracer.log_span_feedback(
                            span_id=synthesis_span.id,
                            score=result.confidence,
                            feedback_type="ocapistaine.correctness",
                            comment=f"compare {len(list_names)} lists",
                        )

                if trace and hasattr(trace, "id") and trace.id:
                    result.trace_id = trace.id
                    trace.update(output={
                        "response": result.response,
                        "model": result.model,
                        "lists_compared": result.lists_compared,
                        "sources_count": len(result.sources),
                    })
                    self._tracer.log_feedback(
                        trace_id=trace.id,
                        score=result.confidence,
                        feedback_type="ocapistaine.rag_confidence",
                        comment=f"compare {list_names}",
                    )

    def _trace_retrieval_span(
        self,
        question: str,
        result_sources: list[dict],
        metrics,
        prov_info: dict,
        span_name: str = "rag_retrieval",
        extra_input: dict | None = None,
    ) -> None:
        """Log a retrieval span with full metrics and feedback scores."""
        span_input = {"query": question}
        if extra_input:
            span_input.update(extra_input)

        with self._tracer.span(
            name=span_name,
            input=span_input,
            span_type="tool",
            provider_info=prov_info,
        ) as retrieval_span:
            if metrics:
                retrieval_span.update(output={
                    "chunks_found": metrics.chunks_found,
                    "best_distance": metrics.best_distance,
                    "mean_distance": metrics.mean_distance,
                    "distance_spread": metrics.distance_spread,
                    "distance_gap_1_2": metrics.distance_gap_1_2,
                    "unique_docs": metrics.unique_docs,
                    "unique_lists": metrics.unique_lists,
                    "unique_categories": metrics.unique_categories,
                    "list_names": metrics.list_names,
                    "total_context_chars": metrics.total_context_chars,
                    "mean_chunk_chars": metrics.mean_chunk_chars,
                    "above_threshold_count": metrics.above_threshold_count,
                    "distances": metrics.distances,
                    "doc_ids": metrics.doc_ids,
                })
                if hasattr(retrieval_span, "id") and retrieval_span.id:
                    # Retrieval confidence: how close was the best match?
                    self._tracer.log_span_feedback(
                        span_id=retrieval_span.id,
                        score=max(0.0, 1.0 - metrics.best_distance),
                        feedback_type="retrieval.confidence",
                        comment=f"{metrics.chunks_found} chunks, best={metrics.best_distance:.3f}",
                    )
                    # Source diversity: unique docs / total chunks
                    diversity = metrics.unique_docs / metrics.chunks_found if metrics.chunks_found else 0
                    self._tracer.log_span_feedback(
                        span_id=retrieval_span.id,
                        score=round(diversity, 3),
                        feedback_type="retrieval.diversity",
                        comment=f"{metrics.unique_docs}/{metrics.chunks_found} unique docs",
                    )
                    # Density: fraction of results below relevance threshold
                    density = metrics.above_threshold_count / metrics.chunks_found if metrics.chunks_found else 0
                    self._tracer.log_span_feedback(
                        span_id=retrieval_span.id,
                        score=round(density, 3),
                        feedback_type="retrieval.density",
                        comment=f"{metrics.above_threshold_count}/{metrics.chunks_found} below threshold",
                    )
            else:
                retrieval_span.update(output={
                    "chunks_found": len(result_sources),
                    "sources": [s.get("doc_id", "") for s in result_sources],
                })

    _OPENAI_PROV = {"provider": "openai", "model_key": "gpt-4o-mini", "model_id": "gpt-4o-mini"}

    def _trace_preprocess_spans(
        self,
        refine_result: RefineResult,
        prov_info: dict,
    ) -> None:
        """Log wording correction and query refinement as separate Opik spans."""
        # Wording correction span (name fixes, spelling, grammar)
        if refine_result.was_corrected:
            with self._tracer.span(
                name="query_wording",
                input={"original_query": refine_result.original},
                span_type="llm",
                provider_info=self._OPENAI_PROV,
            ) as wording_span:
                wording_span.update(output={
                    "corrected_query": refine_result.query,
                    "corrections": refine_result.corrections,
                    "corrections_count": len(refine_result.corrections),
                })

        # Semantic refinement span (vague → precise reformulation)
        if refine_result.was_refined:
            with self._tracer.span(
                name="query_refine",
                input={"original_query": refine_result.original},
                span_type="llm",
                provider_info=self._OPENAI_PROV,
            ) as refine_span:
                refine_span.update(output={
                    "refined_query": refine_result.query,
                    "original_length": len(refine_result.original),
                    "refined_length": len(refine_result.query),
                })
