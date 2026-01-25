"""
LLM Provider Abstraction Layer

Defines the base interface for all LLM providers (Gemini, Claude, Mistral, Ollama).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class Message:
    """Represents a chat message."""

    role: str  # "system", "user", or "assistant"
    content: str


@dataclass
class CompletionResponse:
    """Response from an LLM completion request."""

    content: str
    model: str
    usage: dict = field(default_factory=dict)
    raw_response: object = None

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "model": self.model,
            "usage": self.usage,
        }


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers must implement:
    - complete(): For single request/response completions
    - stream(): For streaming responses (optional, raises NotImplementedError by default)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        """Current model being used."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> CompletionResponse:
        """
        Generate a completion for the given messages.

        Args:
            messages: List of Message objects (system, user, assistant).
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens in response (provider default if None).
            json_mode: If True, instruct model to output valid JSON.

        Returns:
            CompletionResponse with generated content.
        """
        ...

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a completion for the given messages.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Yields:
            String chunks as they are generated.

        Raises:
            NotImplementedError: If provider doesn't support streaming.
        """
        raise NotImplementedError(f"{self.name} does not support streaming")
        yield  # Make this a generator

    def clean_json_response(self, text: str) -> str:
        """
        Strip markdown fences and whitespace from LLM JSON output.

        Args:
            text: Raw LLM response text.

        Returns:
            Cleaned JSON string.
        """
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()
