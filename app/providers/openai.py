"""
OpenAI Provider

Async LLM provider for OpenAI's GPT models with rate limiting and retry logic.
"""

import asyncio
import time

from openai import AsyncOpenAI

from .base import LLMProvider, Message, CompletionResponse
from .config import get_config
from .logging import get_provider_logger


class OpenAIProvider(LLMProvider):
    """
    OpenAI provider with throttling and retry logic.

    Uses the official openai Python SDK.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        rate_limit: float | None = None,
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: Optional API key override.
            model: Optional model name override.
            rate_limit: Minimum seconds between API calls.

        Raises:
            ValueError: If no API key is available.
        """
        config = get_config()
        key = api_key or config.openai_api_key
        if not key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        self._client = AsyncOpenAI(api_key=key)
        self._model_name = model or config.openai_model
        self._rate_limit = rate_limit or config.openai_rate_limit
        self._last_call = 0.0
        self._lock = asyncio.Lock()
        self._logger = get_provider_logger("openai")

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model_name

    async def _throttle(self):
        """
        Async throttling to respect rate limits.

        Uses a lock to ensure proper timing across concurrent calls.
        """
        async with self._lock:
            now = time.monotonic()
            wait = self._rate_limit - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> CompletionResponse:
        """
        Generate completion using OpenAI with retry logic.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            json_mode: If True, model will output JSON.

        Returns:
            CompletionResponse with generated content.
        """
        # Convert to OpenAI message format
        openai_messages = []
        for msg in messages:
            openai_messages.append({"role": msg.role, "content": msg.content})

        # Build request kwargs
        kwargs = {
            "model": self._model_name,
            "messages": openai_messages,
            "temperature": temperature,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # Log request
        self._logger.log_request(
            model=self._model_name,
            temperature=temperature,
            json_mode=json_mode,
        )

        start_time = time.monotonic()

        # Retry loop with exponential backoff
        for attempt in range(3):
            await self._throttle()
            try:
                response = await self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""

                if json_mode:
                    content = self.clean_json_response(content)

                # Log successful response
                latency_ms = (time.monotonic() - start_time) * 1000
                self._logger.log_response(
                    model=self._model_name,
                    latency_ms=latency_ms,
                    output_tokens=response.usage.completion_tokens if response.usage else 0,
                )

                return CompletionResponse(
                    content=content,
                    model=self._model_name,
                    usage={
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                    },
                    raw_response=response,
                )

            except Exception as e:
                error_msg = str(e)

                # Check for rate limit errors
                if "rate_limit" in error_msg.lower() or "429" in error_msg:
                    delay = 30.0 if attempt < 2 else 60.0

                    if attempt == 2:
                        self._logger.log_error(
                            error_type="RATE_LIMIT",
                            message="Rate limit exceeded after 3 retries",
                            model=self._model_name,
                        )
                        raise RuntimeError(f"OpenAI rate limit after 3 retries")

                    self._logger.log_error(
                        error_type="RATE_LIMIT",
                        message=f"Rate limit - retrying after {delay}s (attempt {attempt + 1}/3)",
                        model=self._model_name,
                        retry_after=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                elif "401" in error_msg or "invalid_api_key" in error_msg.lower():
                    self._logger.log_error(
                        error_type="AUTH_ERROR",
                        message="Authentication failed - check API key",
                        model=self._model_name,
                        details={"raw_error": error_msg[:200]},
                    )
                    raise

                elif "insufficient_quota" in error_msg.lower():
                    self._logger.log_error(
                        error_type="QUOTA_EXHAUSTED",
                        message="Quota exhausted - no credits remaining",
                        model=self._model_name,
                    )
                    raise RuntimeError("OpenAI quota exhausted")

                else:
                    self._logger.log_error(
                        error_type="API_ERROR",
                        message=f"API error: {error_msg[:200]}",
                        model=self._model_name,
                    )

                if attempt == 2:
                    self._logger.log_error(
                        error_type="API_ERROR",
                        message="All retries exhausted",
                        model=self._model_name,
                    )
                    raise RuntimeError(f"OpenAI API error after 3 retries: {error_msg[:200]}")

                await asyncio.sleep(2 ** attempt)

        raise RuntimeError("OpenAI retries exhausted")

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ):
        """
        Stream completion using OpenAI.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Yields:
            String chunks as they are generated.
        """
        # Convert to OpenAI message format
        openai_messages = []
        for msg in messages:
            openai_messages.append({"role": msg.role, "content": msg.content})

        kwargs = {
            "model": self._model_name,
            "messages": openai_messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        await self._throttle()
        stream = await self._client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
