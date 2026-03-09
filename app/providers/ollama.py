"""
Ollama Provider

Async LLM provider for local Ollama instances.
Supports resource controls: keep_alive, num_thread, num_ctx.
"""

import httpx

from .base import LLMProvider, Message, CompletionResponse
from .config import get_config


class OllamaProvider(LLMProvider):
    """
    Ollama provider for local LLM inference.

    Connects to a local Ollama instance via HTTP API.

    Resource controls (via .env or constructor):
        OLLAMA_KEEP_ALIVE: How long to keep model loaded after use ("0"=unload immediately, "2m"=default)
        OLLAMA_NUM_THREAD: CPU threads to use (None=all cores)
        OLLAMA_NUM_CTX: Context window size (None=model default, e.g. 2048)
    """

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        keep_alive: str | None = None,
        num_thread: int | None = None,
        num_ctx: int | None = None,
    ):
        config = get_config()
        self._host = (host or config.ollama_host).rstrip("/")
        self._model_name = model or config.ollama_model
        self._timeout = timeout
        self._keep_alive = keep_alive or config.ollama_keep_alive
        self._num_thread = num_thread or config.ollama_num_thread
        self._num_ctx = num_ctx or config.ollama_num_ctx

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model_name

    def _build_options(self, temperature: float, max_tokens: int | None = None) -> dict:
        """Build Ollama options dict with resource controls."""
        options = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        if self._num_thread:
            options["num_thread"] = self._num_thread
        if self._num_ctx:
            options["num_ctx"] = self._num_ctx
        return options

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> CompletionResponse:
        """
        Generate completion using local Ollama.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response (maps to num_predict).
            json_mode: If True, request JSON format.

        Returns:
            CompletionResponse with generated content.
        """
        # Convert to Ollama message format
        ollama_messages = []
        for msg in messages:
            ollama_messages.append({"role": msg.role, "content": msg.content})

        # Add JSON instruction if needed
        if json_mode and ollama_messages:
            last_user_idx = None
            for i in range(len(ollama_messages) - 1, -1, -1):
                if ollama_messages[i]["role"] == "user":
                    last_user_idx = i
                    break
            if last_user_idx is not None:
                ollama_messages[last_user_idx]["content"] += (
                    "\n\nRespond with valid JSON only, no additional text."
                )

        payload = {
            "model": self._model_name,
            "messages": ollama_messages,
            "stream": False,
            "options": self._build_options(temperature, max_tokens),
            "keep_alive": self._keep_alive,
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._host}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data.get("message", {}).get("content", "")
        if json_mode:
            content = self.clean_json_response(content)

        return CompletionResponse(
            content=content,
            model=self._model_name,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            raw_response=data,
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ):
        """
        Stream completion using local Ollama.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Yields:
            String chunks as they are generated.
        """
        ollama_messages = []
        for msg in messages:
            ollama_messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": self._model_name,
            "messages": ollama_messages,
            "stream": True,
            "options": self._build_options(temperature, max_tokens),
            "keep_alive": self._keep_alive,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._host}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        import json
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content

    async def unload(self) -> bool:
        """
        Explicitly unload the model from memory.

        Sends keep_alive=0 to force immediate unload.
        Useful after batch jobs or when switching models.

        Returns:
            True if unload succeeded.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._host}/api/chat",
                    json={
                        "model": self._model_name,
                        "messages": [],
                        "keep_alive": 0,
                    },
                )
                return response.status_code == 200
        except Exception:
            return False

    async def health_check(self) -> bool:
        """
        Check if Ollama is running and the model is available.

        Returns:
            True if Ollama is healthy and model exists, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._host}/api/tags")
                response.raise_for_status()
                data = response.json()
                models = [m.get("name") for m in data.get("models", [])]
                # Check if our model (or base name) is available
                model_base = self._model_name.split(":")[0]
                return any(
                    model_base in m or self._model_name in m for m in models
                )
        except Exception:
            return False
