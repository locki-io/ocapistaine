"""
RAG Feature Base — shared retrieval and context-building logic.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.providers import LLMProvider, Message
from app.rag import retrieval
from ..models import RetrievalMetrics


# Slug → official list name (for prompts and LLM context)
LIST_NAMES = {
    "audierne2026": "Audierne-Esquibien 2026",
    "ca": "Construire l'Avenir",
    "paa": "Passons à l'Action !",
    "spae": "S'unir pour Audierne-Esquibien",
    "csnf": "Cap sur Notre Futur",
}


def display_name(slug: str) -> str:
    """Return the official list name for a slug, or the slug itself as fallback."""
    return LIST_NAMES.get(slug, slug)


class RAGFeatureBase(ABC):
    """Base class for OCapistaine RAG features."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def prompt(self) -> str: ...

    @abstractmethod
    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        **kwargs,
    ) -> Any: ...

    def _build_context(self, results: list[retrieval.RetrievalResult]) -> str:
        """Build LLM context string from retrieval results."""
        parts = []
        for r in results:
            label = r.metadata.get("title") or r.metadata.get("doc_id", "")
            cat = r.metadata.get("category", "")
            list_slug = r.metadata.get("list_name", "")
            header_parts = [f"[{label}]"]
            if list_slug:
                header_parts.append(f"({display_name(list_slug)})")
            if cat:
                header_parts.append(f"({cat})")
            parts.append(f"{' '.join(header_parts)}\n{r.content}")
        return "\n---\n".join(parts)

    def _deduplicate_sources(
        self, results: list[retrieval.RetrievalResult]
    ) -> list[dict]:
        """Deduplicate sources by doc_id."""
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
        return sources

    # Distance below which a chunk is considered "confidently relevant"
    # Calibrated for all-MiniLM-L6-v2 on French civic content (generic model).
    # With French-optimized embeddings, tighten back to 0.5.
    _RELEVANCE_THRESHOLD = 0.55

    def _compute_retrieval_metrics(
        self, results: list[retrieval.RetrievalResult],
    ) -> RetrievalMetrics:
        """Compute retrieval quality metrics from raw results (no LLM call needed)."""
        if not results:
            return RetrievalMetrics()

        distances = [r.distance for r in results]
        doc_ids = [r.metadata.get("doc_id", "") for r in results]
        list_names_set = set(r.metadata.get("list_name", "") for r in results)
        categories_set = set(r.metadata.get("category", "") for r in results)
        total_chars = sum(len(r.content) for r in results)

        return RetrievalMetrics(
            chunks_found=len(results),
            best_distance=round(min(distances), 4),
            mean_distance=round(sum(distances) / len(distances), 4),
            distance_spread=round(max(distances) - min(distances), 4),
            distance_gap_1_2=round(distances[1] - distances[0], 4) if len(distances) > 1 else 0.0,
            unique_docs=len(set(doc_ids)),
            unique_lists=len(list_names_set - {""}),
            unique_categories=len(categories_set - {""}),
            list_names=sorted(list_names_set - {""}),
            total_context_chars=total_chars,
            mean_chunk_chars=round(total_chars / len(results)),
            above_threshold_count=sum(1 for d in distances if d < self._RELEVANCE_THRESHOLD),
            distances=[round(d, 4) for d in distances],
            doc_ids=doc_ids,
        )

    async def _complete(
        self,
        provider: LLMProvider,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1500,
        history: list[dict] | None = None,
    ) -> tuple[str, str, dict]:
        """Complete with provider, return (content, model, usage)."""
        messages = self._build_messages(system_prompt, user_prompt, history)
        response = await provider.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content, response.model, response.usage

    def _build_messages(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[dict] | None = None,
    ) -> list[Message]:
        """
        Build message list with optional conversation history.

        History is injected between system prompt and current user message
        so the LLM has conversational context for follow-up questions.

        Args:
            system_prompt: System/persona prompt
            user_prompt: Current user prompt (with RAG context)
            history: List of {"role": "user"|"assistant", "content": str}
        """
        messages = [Message(role="system", content=system_prompt)]
        if history:
            for turn in history:
                messages.append(Message(role=turn["role"], content=turn["content"]))
        messages.append(Message(role="user", content=user_prompt))
        return messages
