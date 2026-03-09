"""
RAG Feature Base — shared retrieval and context-building logic.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.providers import LLMProvider, Message
from app.rag import retrieval


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
