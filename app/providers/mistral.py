"""
Mistral AI Provider

Async LLM provider for Mistral AI models.
"""

from .base import LLMProvider, Message, CompletionResponse
from .config import get_config


class MistralProvider(LLMProvider):
    """
    Mistral AI provider using the official SDK.

    Supports Mistral models (tiny, small, medium, large).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """
        Initialize Mistral provider.

        Args:
            api_key: Optional API key override.
            model: Optional model name override.

        Raises:
            ValueError: If no API key is available.
            ImportError: If mistralai SDK is not installed.
        """
        try:
            from mistralai import Mistral
        except ImportError:
            raise ImportError(
                "mistralai package required. Install with: pip install mistralai"
            )

        config = get_config()
        key = api_key or config.mistral_api_key
        if not key:
            raise ValueError("MISTRAL_API_KEY not found in environment")

        self._client = Mistral(api_key=key)
        self._model_name = model or config.mistral_model

    @property
    def name(self) -> str:
        return "mistral"

    @property
    def model(self) -> str:
        return self._model_name

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> CompletionResponse:
        """
        Generate completion using Mistral.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            json_mode: If True, instruct model to output JSON.

        Returns:
            CompletionResponse with generated content.
        """
        # Convert to Mistral message format
        mistral_messages = []
        for msg in messages:
            mistral_messages.append({"role": msg.role, "content": msg.content})

        # Add JSON instruction if needed
        if json_mode and mistral_messages:
            last_user_idx = None
            for i in range(len(mistral_messages) - 1, -1, -1):
                if mistral_messages[i]["role"] == "user":
                    last_user_idx = i
                    break
            if last_user_idx is not None:
                mistral_messages[last_user_idx]["content"] += (
                    "\n\nRespond with valid JSON only, no additional text."
                )

        kwargs = {
            "model": self._model_name,
            "messages": mistral_messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        # Use async chat completion
        response = await self._client.chat.complete_async(**kwargs)

        content = response.choices[0].message.content
        if json_mode:
            content = self.clean_json_response(content)

        return CompletionResponse(
            content=content,
            model=self._model_name,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            raw_response=response,
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ):
        """
        Stream completion using Mistral.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Yields:
            String chunks as they are generated.
        """
        mistral_messages = []
        for msg in messages:
            mistral_messages.append({"role": msg.role, "content": msg.content})

        kwargs = {
            "model": self._model_name,
            "messages": mistral_messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        async for chunk in await self._client.chat.stream_async(**kwargs):
            if chunk.data.choices and chunk.data.choices[0].delta.content:
                yield chunk.data.choices[0].delta.content
