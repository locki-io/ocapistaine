"""
RAG Chat Feature — citizen Q&A with retrieval.
"""

from typing import AsyncIterator

from app.providers import LLMProvider
from app.providers.logging import get_provider_logger
from app.providers.pricing import compute_cost
from app.rag import retrieval

_cost_logger = get_provider_logger("chat")
from app.rag.prompts import (
    SYSTEM_PROMPT,
    RAG_USER_TEMPLATE,
    OVERVIEW_SYSTEM_PROMPT,
    OVERVIEW_USER_TEMPLATE,
)

from ..models import ChatResult
from .base import RAGFeatureBase

# Keywords that signal a broad/overview question
_OVERVIEW_KEYWORDS = [
    "municipales", "élections", "listes", "candidats", "que sais-tu",
    "vue d'ensemble", "résumé", "présente", "quelles listes", "qui se présente",
    "combien de listes", "overview", "général",
]


def _is_overview_question(question: str) -> bool:
    q = question.lower()
    return sum(1 for kw in _OVERVIEW_KEYWORDS if kw in q) >= 2


class RAGChatFeature(RAGFeatureBase):
    """Citizen Q&A: retrieve relevant chunks and synthesize an answer."""

    @property
    def name(self) -> str:
        return "rag_chat"

    @property
    def prompt(self) -> str:
        return RAG_USER_TEMPLATE

    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        question: str = "",
        n_results: int = 10,
        filters: dict | None = None,
        history: list[dict] | None = None,
        **kwargs,
    ) -> ChatResult:
        """
        Execute RAG chat query.

        Args:
            provider: LLM provider for synthesis
            system_prompt: Agent persona prompt
            question: User question
            n_results: Number of chunks to retrieve
            filters: Optional metadata filters (e.g. {"list_name": "paa"})
            history: Conversation history for follow-up context
        """
        if not question:
            return ChatResult(
                response="Veuillez poser une question.",
                confidence=0.0,
            )

        is_overview = _is_overview_question(question) and not filters

        if is_overview:
            results = retrieval.search_overview(question)
        else:
            results = retrieval.search(question, n_results=n_results, where=filters)

        if not results:
            return ChatResult(
                response="Aucun document pertinent trouvé dans la base.",
                sources=[], confidence=0.0, is_overview=is_overview,
            )

        context = self._build_context(results)

        if is_overview:
            sys_prompt = OVERVIEW_SYSTEM_PROMPT
            user_prompt = OVERVIEW_USER_TEMPLATE.format(context=context, question=question)
        else:
            sys_prompt = f"{system_prompt}\n\n{SYSTEM_PROMPT}"
            user_prompt = RAG_USER_TEMPLATE.format(context=context, question=question)

        try:
            content, model, usage = await self._complete(
                provider=provider,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                max_tokens=2500 if is_overview else 1500,
                history=history,
            )
        except Exception as e:
            return ChatResult(
                response=f"Erreur lors de la synthèse : {e}",
                confidence=0.0, is_overview=is_overview,
            )

        sources = self._deduplicate_sources(results)
        metrics = self._compute_retrieval_metrics(results)
        confidence = max(0.0, 1.0 - metrics.best_distance)

        return ChatResult(
            response=content, sources=sources, model=model,
            confidence=round(confidence, 3), is_overview=is_overview,
            retrieval_metrics=metrics, usage=usage,
        )

    async def stream_execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        question: str = "",
        n_results: int = 10,
        filters: dict | None = None,
        history: list[dict] | None = None,
        **kwargs,
    ) -> AsyncIterator[str | ChatResult]:
        """
        Stream RAG chat: retrieve, then stream LLM synthesis token by token.

        Yields str chunks during generation, then a final ChatResult.
        """
        if not question:
            yield ChatResult(response="Veuillez poser une question.", confidence=0.0)
            return

        is_overview = _is_overview_question(question) and not filters

        if is_overview:
            results = retrieval.search_overview(question)
        else:
            results = retrieval.search(question, n_results=n_results, where=filters)

        if not results:
            yield ChatResult(
                response="Aucun document pertinent trouvé dans la base.",
                sources=[], confidence=0.0, is_overview=is_overview,
            )
            return

        context = self._build_context(results)

        if is_overview:
            sys_prompt = OVERVIEW_SYSTEM_PROMPT
            user_prompt = OVERVIEW_USER_TEMPLATE.format(context=context, question=question)
        else:
            sys_prompt = f"{system_prompt}\n\n{SYSTEM_PROMPT}"
            user_prompt = RAG_USER_TEMPLATE.format(context=context, question=question)

        messages = self._build_messages(sys_prompt, user_prompt, history)
        max_tokens = 2500 if is_overview else 1500

        full_response = ""
        try:
            async for chunk in provider.stream(
                messages=messages, temperature=0.3, max_tokens=max_tokens,
            ):
                full_response += chunk
                yield chunk
        except Exception as e:
            yield ChatResult(
                response=f"Erreur lors de la synthèse : {e}",
                confidence=0.0, is_overview=is_overview,
            )
            return

        sources = self._deduplicate_sources(results)
        metrics = self._compute_retrieval_metrics(results)
        confidence = max(0.0, 1.0 - metrics.best_distance)
        model_name = getattr(provider, "model", "unknown")

        # Estimate tokens from char counts (streaming has no usage data)
        est_in = len(user_prompt + sys_prompt) // 4
        est_out = len(full_response) // 4
        cost = compute_cost(model_name, est_in, est_out)
        usage = {"input_tokens": est_in, "output_tokens": est_out, "cost_usd": cost, "estimated": True}
        if cost is not None:
            _cost_logger.log_cost(model_name, est_in, est_out, cost)

        yield ChatResult(
            response=full_response, sources=sources, model=model_name,
            confidence=round(confidence, 3), is_overview=is_overview,
            retrieval_metrics=metrics, usage=usage,
        )
