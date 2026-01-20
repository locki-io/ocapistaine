"""
Google Gemini Provider

Async LLM provider for Google's Gemini models with rate limiting and retry logic.
"""

import asyncio
import re
import time

from .base import LLMProvider, Message, CompletionResponse
from .config import get_config


class GeminiProvider(LLMProvider):
    """
    Google Gemini provider with throttling and retry logic.

    Migrated from charterAgent/charter_agent.py GeminiClient.
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
            RuntimeError: If no compatible models are found.
        """
        import google.generativeai as genai

        config = get_config()
        key = api_key or config.effective_google_key
        if not key:
            raise ValueError(
                "GOOGLE_API_KEY or GEMINI_API_KEY not found in environment"
            )

        genai.configure(api_key=key)

        self._model_name = model or config.gemini_model
        if not self._model_name:
            # Auto-detect first available model
            try:
                models = genai.list_models()
                supported = [
                    m.name
                    for m in models
                    if "generateContent" in getattr(m, "supported_generation_methods", [])
                ]
                if not supported:
                    raise RuntimeError("No Gemini models support generateContent")
                self._model_name = supported[0]
            except Exception as e:
                raise RuntimeError(f"Failed to list Gemini models: {e}")

        self._genai = genai
        self._client = genai.GenerativeModel(self._model_name)
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
            json_mode: If True, model will be instructed to output JSON.

        Returns:
            CompletionResponse with generated content.
        """
        # Convert messages to Gemini format (single prompt string)
        prompt_parts = []
        for msg in messages:
            if msg.role == "system":
                prompt_parts.append(f"Instructions: {msg.content}\n")
            elif msg.role == "user":
                prompt_parts.append(f"User: {msg.content}\n")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}\n")
        prompt = "".join(prompt_parts)

        if json_mode:
            prompt += "\nRespond with valid JSON only."

        generation_config = {"temperature": temperature}
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens

        # Retry loop with exponential backoff
        for attempt in range(3):
            await self._throttle()
            try:
                response = await asyncio.to_thread(
                    self._client.generate_content,
                    prompt,
                    generation_config=generation_config,
                )
                content = response.text
                if json_mode:
                    content = self.clean_json_response(content)

                return CompletionResponse(
                    content=content,
                    model=self._model_name,
                    usage={},  # Gemini doesn't provide detailed usage
                    raw_response=response,
                )
            except Exception as e:
                msg = str(e)
                if "429" in msg and "retry" in msg.lower():
                    # Extract retry delay from error message
                    match = re.search(r"retry in ([0-9.]+)s", msg)
                    delay = float(match.group(1)) if match else 35.0
                    await asyncio.sleep(delay)
                    continue
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError("Gemini retries exhausted")
