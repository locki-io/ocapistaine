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

from .features import RAGChatFeature, RAGCompareFeature
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

        # Execute feature
        result: ChatResult = await self.execute_feature(
            "rag_chat",
            question=question,
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
                input={"question": question},
                metadata={"agent": "ocapistaine", "feature": trace_type, "type": trace_type},
                tags=["rag", "chat", "ocapistaine"],
                provider_info=prov_info,
            ) as trace:

                with self._tracer.span(
                    name="rag_retrieval",
                    input={"query": question, "is_overview": result.is_overview},
                    span_type="tool",
                    provider_info=prov_info,
                ) as retrieval_span:
                    retrieval_span.update(output={
                        "chunks_found": len(result.sources),
                        "sources": [s.get("doc_id", "") for s in result.sources],
                    })

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

        # Execute feature
        result: CompareResult = await self.execute_feature(
            "rag_compare",
            question=question,
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
                input={"question": question, "list_names": list_names},
                metadata={"agent": "ocapistaine", "feature": "rag_compare", "type": "rag_compare"},
                tags=["rag", "compare", "ocapistaine"],
                provider_info=prov_info,
            ) as trace:

                with self._tracer.span(
                    name="rag_compare_retrieval",
                    input={"query": question, "lists": list_names},
                    span_type="tool",
                    provider_info=prov_info,
                ) as retrieval_span:
                    retrieval_span.update(output={
                        "sources_count": len(result.sources),
                        "lists_compared": result.lists_compared,
                    })

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
        feature: RAGChatFeature = self._features["rag_chat"]

        result = None
        async for item in feature.stream_execute(
            provider=self._provider,
            system_prompt=self.persona_prompt,
            question=question,
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
            self._trace_chat(result, question, n_results, filters, thread_id)

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
        feature: RAGCompareFeature = self._features["rag_compare"]

        result = None
        async for item in feature.stream_execute(
            provider=self._provider,
            system_prompt=self.persona_prompt,
            question=question,
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
            self._trace_compare(result, question, list_names, n_per_list, thread_id)

        yield result

    # ── Private tracing helpers ────────────────────────────

    def _trace_chat(
        self,
        result: ChatResult,
        question: str,
        n_results: int,
        filters: dict | None,
        thread_id: str,
    ) -> None:
        """Trace a completed chat result to Opik (within a thread)."""
        trace_type = "rag_overview" if result.is_overview else "rag_chat"
        prov_info = self._get_provider_info()

        with self._tracer.start_thread(thread_id):
            with self._tracer.start_trace(
                name=trace_type,
                input={"question": question},
                metadata={"agent": "ocapistaine", "feature": trace_type, "type": trace_type},
                tags=["rag", "chat", "ocapistaine"],
                provider_info=prov_info,
            ) as trace:
                with self._tracer.span(
                    name="rag_retrieval",
                    input={"query": question, "is_overview": result.is_overview},
                    span_type="tool",
                    provider_info=prov_info,
                ) as retrieval_span:
                    retrieval_span.update(output={
                        "chunks_found": len(result.sources),
                        "sources": [s.get("doc_id", "") for s in result.sources],
                    })

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
    ) -> None:
        """Trace a completed compare result to Opik (within a thread)."""
        prov_info = self._get_provider_info()

        with self._tracer.start_thread(thread_id):
            with self._tracer.start_trace(
                name="rag_compare",
                input={"question": question, "list_names": list_names},
                metadata={"agent": "ocapistaine", "feature": "rag_compare", "type": "rag_compare"},
                tags=["rag", "compare", "ocapistaine"],
                provider_info=prov_info,
            ) as trace:
                with self._tracer.span(
                    name="rag_compare_retrieval",
                    input={"query": question, "lists": list_names},
                    span_type="tool",
                    provider_info=prov_info,
                ) as retrieval_span:
                    retrieval_span.update(output={
                        "sources_count": len(result.sources),
                        "lists_compared": result.lists_compared,
                    })

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
