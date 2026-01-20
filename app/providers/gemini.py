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

                return CompletionResponse(
                    content=content,
                    model=self._model_name,
                    usage={},
                    raw_response=response,
                )
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    # Rate limited - extract retry delay if available
                    match = re.search(r"retry.+?([0-9.]+)\s*s", msg, re.IGNORECASE)
                    delay = float(match.group(1)) if match else 35.0
                    await asyncio.sleep(delay)
                    continue
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError("Gemini retries exhausted")
