"""
RAG Compare Feature — cross-list program comparison.
"""

import random
from typing import AsyncIterator

from app.providers import LLMProvider
from app.providers.logging import get_provider_logger
from app.providers.pricing import compute_cost
from app.services.cost import record_cost
from app.rag import retrieval

_cost_logger = get_provider_logger("compare")
from app.rag.prompts import COMPARE_SYSTEM_PROMPT, COMPARE_USER_TEMPLATE

from ..models import CompareResult
from .base import RAGFeatureBase, display_name


class RAGCompareFeature(RAGFeatureBase):
    """Compare electoral programs across lists on a given topic."""

    @property
    def name(self) -> str:
        return "rag_compare"

    @property
    def prompt(self) -> str:
        return COMPARE_USER_TEMPLATE

    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        question: str = "",
        list_names: list[str] | None = None,
        n_per_list: int = 5,
        history: list[dict] | None = None,
        **kwargs,
    ) -> CompareResult:
        """
        Compare electoral programs across lists.

        Args:
            provider: LLM provider for synthesis
            system_prompt: Agent persona prompt
            question: Comparison topic/question
            list_names: Lists to compare
            n_per_list: Chunks per list

        Returns:
            CompareResult with response, sources, lists compared
        """
        if not question or not list_names:
            return CompareResult(
                response="Question et listes requises pour la comparaison.",
                confidence=0.0,
            )

        # Multi-list retrieval
        results_by_list = retrieval.search_compare(question, list_names, n_per_list)

        # Shuffle list order to avoid systematic bias (neutrality)
        shuffled_names = list(results_by_list.keys())
        random.shuffle(shuffled_names)

        # Build context per list
        list_context_parts = []
        all_sources = []
        all_results = []
        for name in shuffled_names:
            results = results_by_list[name]
            if results:
                all_results.extend(results)
                excerpts = "\n".join(r.content for r in results)
                list_context_parts.append(f"### {display_name(name)}\n{excerpts}")
                for r in results:
                    all_sources.append({
                        "doc_id": r.metadata.get("doc_id", ""),
                        "title": r.metadata.get("title", ""),
                        "list_name": name,
                        "distance": r.distance,
                    })
            else:
                list_context_parts.append(f"### {display_name(name)}\n(Aucun document trouvé)")

        metrics = self._compute_retrieval_metrics(all_results) if all_results else None
        list_contexts = "\n\n".join(list_context_parts)

        sys_prompt = f"{system_prompt}\n\n{COMPARE_SYSTEM_PROMPT}"
        user_prompt = COMPARE_USER_TEMPLATE.format(
            list_contexts=list_contexts, question=question
        )

        try:
            content, model, usage = await self._complete(
                provider=provider,
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                max_tokens=2000,
                history=history,
            )
        except Exception as e:
            return CompareResult(
                response=f"Erreur lors de la comparaison : {e}",
                lists_compared=list_names,
                confidence=0.0,
            )

        confidence = max(0.0, 1.0 - metrics.best_distance) if metrics else 0.7

        cost_usd = usage.get("cost_usd") if usage else None
        if cost_usd is not None:
            record_cost(cost_usd, model)

        return CompareResult(
            response=content,
            lists_compared=list_names,
            sources=all_sources,
            model=model,
            confidence=round(confidence, 3),
            retrieval_metrics=metrics,
            usage=usage,
        )

    async def stream_execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        question: str = "",
        list_names: list[str] | None = None,
        n_per_list: int = 5,
        history: list[dict] | None = None,
        **kwargs,
    ) -> AsyncIterator[str | CompareResult]:
        """
        Stream compare: retrieve per list, then stream LLM synthesis.

        Yields str chunks during generation, then a final CompareResult.
        """
        if not question or not list_names:
            yield CompareResult(
                response="Question et listes requises pour la comparaison.",
                confidence=0.0,
            )
            return

        results_by_list = retrieval.search_compare(question, list_names, n_per_list)

        # Shuffle list order to avoid systematic bias (neutrality)
        shuffled_names = list(results_by_list.keys())
        random.shuffle(shuffled_names)

        list_context_parts = []
        all_sources = []
        all_results = []
        for name in shuffled_names:
            results = results_by_list[name]
            if results:
                all_results.extend(results)
                excerpts = "\n".join(r.content for r in results)
                list_context_parts.append(f"### {display_name(name)}\n{excerpts}")
                for r in results:
                    all_sources.append({
                        "doc_id": r.metadata.get("doc_id", ""),
                        "title": r.metadata.get("title", ""),
                        "list_name": name,
                        "distance": r.distance,
                    })
            else:
                list_context_parts.append(f"### {display_name(name)}\n(Aucun document trouvé)")

        metrics = self._compute_retrieval_metrics(all_results) if all_results else None
        list_contexts = "\n\n".join(list_context_parts)

        sys_prompt = f"{system_prompt}\n\n{COMPARE_SYSTEM_PROMPT}"
        user_prompt = COMPARE_USER_TEMPLATE.format(
            list_contexts=list_contexts, question=question
        )

        messages = self._build_messages(sys_prompt, user_prompt, history)

        full_response = ""
        try:
            async for chunk in provider.stream(
                messages=messages,
                temperature=0.3,
                max_tokens=2000,
            ):
                full_response += chunk
                yield chunk
        except Exception as e:
            yield CompareResult(
                response=f"Erreur lors de la comparaison : {e}",
                lists_compared=list_names,
                confidence=0.0,
            )
            return

        model_name = getattr(provider, "model", "unknown")
        confidence = max(0.0, 1.0 - metrics.best_distance) if metrics else 0.7

        # Estimate tokens from char counts (streaming has no usage data)
        est_in = len(user_prompt + sys_prompt) // 4
        est_out = len(full_response) // 4
        cost = compute_cost(model_name, est_in, est_out)
        usage = {"input_tokens": est_in, "output_tokens": est_out, "cost_usd": cost, "estimated": True}
        if cost is not None:
            _cost_logger.log_cost(model_name, est_in, est_out, cost)
            record_cost(cost, model_name)

        yield CompareResult(
            response=full_response,
            lists_compared=list_names,
            sources=all_sources,
            model=model_name,
            confidence=round(confidence, 3),
            retrieval_metrics=metrics,
            usage=usage,
        )
