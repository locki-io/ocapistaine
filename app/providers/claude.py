"""
Anthropic Claude Provider

Async LLM provider for Anthropic's Claude models.
"""

from .base import LLMProvider, Message, CompletionResponse
from .config import get_config


class ClaudeProvider(LLMProvider):
    """
    Anthropic Claude provider using the official SDK.

    Supports Claude 3 family models (Haiku, Sonnet, Opus).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """
        Initialize Claude provider.

        Args:
            api_key: Optional API key override.
            model: Optional model name override.

        Raises:
            ValueError: If no API key is available.
            ImportError: If anthropic SDK is not installed.
        """
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install anthropic"
            )

        config = get_config()
        key = api_key or config.anthropic_api_key
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self._client = anthropic.Anthropic(api_key=key)
        self._async_client = anthropic.AsyncAnthropic(api_key=key)
        self._model_name = model or config.claude_model

    @property
    def name(self) -> str:
        return "claude"

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
        Generate completion using Claude.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response (default 1024).
            json_mode: If True, instruct model to output JSON.

        Returns:
            CompletionResponse with generated content.
        """
        # Separate system message from conversation
        system_content = None
        conversation = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                conversation.append({"role": msg.role, "content": msg.content})

        # Claude requires at least one user message
        if not conversation:
            conversation = [{"role": "user", "content": "Hello"}]

        # Add JSON instruction to last user message if json_mode
        if json_mode and conversation:
            last_user_idx = None
            for i in range(len(conversation) - 1, -1, -1):
                if conversation[i]["role"] == "user":
                    last_user_idx = i
                    break
            if last_user_idx is not None:
                conversation[last_user_idx]["content"] += (
                    "\n\nRespond with valid JSON only, no additional text."
                )

        kwargs = {
            "model": self._model_name,
            "messages": conversation,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }
        if system_content:
            kwargs["system"] = system_content

        response = await self._async_client.messages.create(**kwargs)

        content = response.content[0].text
        if json_mode:
            content = self.clean_json_response(content)

        return CompletionResponse(
            content=content,
            model=self._model_name,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
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
        Stream completion using Claude.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Yields:
            String chunks as they are generated.
        """
        # Separate system message from conversation
        system_content = None
        conversation = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                conversation.append({"role": msg.role, "content": msg.content})

        if not conversation:
            conversation = [{"role": "user", "content": "Hello"}]

        kwargs = {
            "model": self._model_name,
            "messages": conversation,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }
        if system_content:
            kwargs["system"] = system_content

        async with self._async_client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
