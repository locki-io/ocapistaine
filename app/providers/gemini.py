"""
Google Gemini Provider

Async LLM provider for Google's Gemini models with rate limiting and retry logic.
Uses the new google-genai SDK.
"""

import asyncio
import re
import time

from google import genai
from google.genai import types

from .base import LLMProvider, Message, CompletionResponse
from .config import get_config
from .logging import get_provider_logger


class GeminiProvider(LLMProvider):
    """
    Google Gemini provider with throttling and retry logic.

    Uses the new google-genai SDK (replacing deprecated google-generativeai).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        rate_limit: float | None = None,
    ):
        """
        Initialize Gemini provider.

        Args:
            api_key: Optional API key override.
            model: Optional model name override.
            rate_limit: Minimum seconds between API calls.

        Raises:
            ValueError: If no API key is available.
        """
        config = get_config()
        key = api_key or config.effective_google_key
        if not key:
            raise ValueError(
                "GOOGLE_API_KEY or GEMINI_API_KEY not found in environment"
            )

        self._client = genai.Client(api_key=key)
        self._model_name = model or config.gemini_model
        self._rate_limit = rate_limit or config.gemini_rate_limit
        self._last_call = 0.0
        self._lock = asyncio.Lock()
        self._logger = get_provider_logger("gemini")

    @property
    def name(self) -> str:
        return "gemini"

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
        Generate completion using Gemini with retry logic.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens (maps to max_output_tokens).
            json_mode: If True, model will output JSON.

        Returns:
            CompletionResponse with generated content.
        """
        # Build contents from messages
        system_instruction = None
        contents = []

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            elif msg.role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=msg.content)]
                ))
            elif msg.role == "assistant":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=msg.content)]
                ))

        # Build generation config
        generation_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else None,
        )

        if system_instruction:
            generation_config.system_instruction = system_instruction

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
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=self._model_name,
                    contents=contents,
                    config=generation_config,
                )
                content = response.text
                if json_mode:
                    content = self.clean_json_response(content)

                # Log successful response
                latency_ms = (time.monotonic() - start_time) * 1000
                self._logger.log_response(
                    model=self._model_name,
                    latency_ms=latency_ms,
                )

                return CompletionResponse(
                    content=content,
                    model=self._model_name,
                    usage={},
                    raw_response=response,
                )
            except Exception as e:
                error_msg = str(e)

                # Check for quota exhausted
                if "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
                    # Parse error details
                    if "limit: 0" in error_msg:
                        self._logger.log_error(
                            error_type="QUOTA_EXHAUSTED",
                            message="Daily quota exhausted - no credits remaining",
                            model=self._model_name,
                            details={"raw_error": error_msg[:500]},
                        )
                    else:
                        self._logger.log_error(
                            error_type="RATE_LIMIT",
                            message="Rate limit exceeded",
                            model=self._model_name,
                        )

                    # Extract retry delay if available
                    match = re.search(r"retry.+?([0-9.]+)\s*s", error_msg, re.IGNORECASE)
                    delay = float(match.group(1)) if match else 35.0
                    self._logger.log_error(
                        error_type="RATE_LIMIT",
                        message=f"Retrying after {delay}s (attempt {attempt + 1}/3)",
                        model=self._model_name,
                        retry_after=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                elif "429" in error_msg:
                    match = re.search(r"retry.+?([0-9.]+)\s*s", error_msg, re.IGNORECASE)
                    delay = float(match.group(1)) if match else 35.0
                    self._logger.log_error(
                        error_type="RATE_LIMIT",
                        message=f"HTTP 429 - retrying after {delay}s",
                        model=self._model_name,
                        retry_after=delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                elif "401" in error_msg or "403" in error_msg:
                    self._logger.log_error(
                        error_type="AUTH_ERROR",
                        message="Authentication failed - check API key",
                        model=self._model_name,
                        details={"raw_error": error_msg[:200]},
                    )
                    raise

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
                    raise
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError("Gemini retries exhausted")
