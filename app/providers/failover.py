"""
Provider Failover Utility

Automatic failover from local Ollama to external LLM providers when unavailable.
"""

from typing import Callable, TypeVar

from .base import LLMProvider, Message, CompletionResponse
from .config import get_config, ProviderName
from .logging import get_provider_logger

logger = get_provider_logger(__name__)

T = TypeVar("T")

# Default failover chain: local -> paid (reliable) -> free tier (rate limited)
# OpenAI and Claude are more reliable than Gemini which has aggressive rate limits
DEFAULT_FAILOVER_CHAIN = ["ollama", "openai", "claude", "mistral", "gemini"]


class ProviderWithFailover:
    """
    Provider wrapper that automatically fails over to backup providers.

    When the primary provider (usually Ollama) is unavailable or returns an error,
    this wrapper automatically tries the next provider in the failover chain.

    Example:
        provider = ProviderWithFailover(
            primary="ollama",
            failover_chain=["gemini", "mistral"],
        )
        response = await provider.complete(messages)
    """

    def __init__(
        self,
        primary: ProviderName = "ollama",
        failover_chain: list[ProviderName] | None = None,
        enable_failover: bool = True,
        model_overrides: dict[str, str] | None = None,
    ):
        """
        Initialize provider with failover support.

        Args:
            primary: Primary provider name (default: ollama)
            failover_chain: List of providers to try on failure
            enable_failover: If False, only use primary (no failover)
            model_overrides: Dict of provider -> model to use
        """
        self._primary = primary
        self._failover_chain = failover_chain or DEFAULT_FAILOVER_CHAIN
        self._enable_failover = enable_failover
        self._model_overrides = model_overrides or {}

        # Build provider chain (primary first, then failover)
        self._chain = [primary]
        if enable_failover:
            for p in self._failover_chain:
                if p != primary and p not in self._chain:
                    self._chain.append(p)

        self._current_provider: LLMProvider | None = None
        self._current_name: str | None = None
        self._failover_occurred: bool = False
        self._errors: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        """Current provider name (actual, after failover)."""
        return self._current_name or self._primary

    @property
    def model(self) -> str:
        """Current model being used."""
        if self._current_provider:
            return self._current_provider.model
        return "unknown"

    @property
    def requested_provider(self) -> str:
        """The provider originally requested (before failover)."""
        return self._primary

    @property
    def failover_occurred(self) -> bool:
        """Whether failover happened on the last call."""
        return self._failover_occurred

    @property
    def failover_errors(self) -> list[tuple[str, str]]:
        """Errors from providers that failed before the successful one."""
        return self._errors.copy()

    def get_provider_info(self) -> dict:
        """
        Get provider metadata for tracing — reflects actual state after execution.

        Returns dict with requested_provider, actual_provider, model, failover flag.
        """
        info = {
            "provider": self._current_name or self._primary,
            "model_key": self.model,
            "model_id": self.model,
            "requested_provider": self._primary,
        }
        if self._failover_occurred:
            info["failover"] = True
            info["failover_from"] = self._primary
            info["failover_errors"] = "; ".join(
                f"{p}: {e}" for p, e in self._errors
            )
        return info

    def _get_provider(self, name: ProviderName) -> LLMProvider:
        """Get a provider instance by name."""
        from . import get_provider

        kwargs = {}
        if name in self._model_overrides:
            kwargs["model"] = self._model_overrides[name]

        return get_provider(name, cache=False, **kwargs)

    async def _check_ollama_available(self) -> bool:
        """Check if Ollama is available and not locked."""
        from .ollama import OllamaProvider

        # Check health
        provider = OllamaProvider()
        is_healthy = await provider.health_check()
        if not is_healthy:
            logger.info("Ollama health check failed")
            return False

        # Check global lock (Redis)
        try:
            from app.services.scheduler.utils import get_scheduler_redis

            redis = get_scheduler_redis()
            lock_key = "lock:ollama:global"
            if redis.exists(lock_key):
                logger.info("Ollama is locked by another task")
                return False
        except Exception as e:
            logger.warning(f"Could not check Ollama lock: {e}")

        return True

    async def _acquire_ollama_lock(self, task_id: str, ttl: int = 300) -> bool:
        """Acquire the global Ollama lock."""
        try:
            from app.services.scheduler.utils import get_scheduler_redis

            redis = get_scheduler_redis()
            lock_key = "lock:ollama:global"
            acquired = redis.set(lock_key, task_id, ex=ttl, nx=True)
            if acquired:
                logger.debug(f"Acquired Ollama lock: {task_id}")
            return bool(acquired)
        except Exception as e:
            logger.warning(f"Could not acquire Ollama lock: {e}")
            return False

    async def _release_ollama_lock(self, task_id: str) -> None:
        """Release the global Ollama lock if we hold it."""
        try:
            from app.services.scheduler.utils import get_scheduler_redis

            redis = get_scheduler_redis()
            lock_key = "lock:ollama:global"
            # Only delete if we hold the lock
            current = redis.get(lock_key)
            if current:
                # Handle both bytes and str returns from Redis
                current_str = current.decode() if isinstance(current, bytes) else current
                if current_str == task_id:
                    redis.delete(lock_key)
                    logger.debug(f"Released Ollama lock: {task_id}")
        except Exception as e:
            logger.warning(f"Could not release Ollama lock: {e}")

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
        task_id: str | None = None,
    ) -> CompletionResponse:
        """
        Generate completion with automatic failover.

        Args:
            messages: List of Message objects.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            json_mode: If True, request JSON format.
            task_id: Optional task ID for locking (used with Ollama).

        Returns:
            CompletionResponse with generated content.

        Raises:
            Exception: If all providers in chain fail.
        """
        errors = []
        ollama_locked = False
        self._failover_occurred = False
        self._errors = []

        for provider_name in self._chain:
            try:
                # Special handling for Ollama
                if provider_name == "ollama":
                    # Check if Ollama is available
                    if not await self._check_ollama_available():
                        logger.info(
                            f"Skipping Ollama (unavailable), trying next provider"
                        )
                        errors.append(("ollama", "unavailable or locked"))
                        continue

                    # Try to acquire lock if task_id provided
                    if task_id:
                        if not await self._acquire_ollama_lock(task_id):
                            logger.info(
                                "Could not acquire Ollama lock, trying next provider"
                            )
                            errors.append(("ollama", "lock acquisition failed"))
                            continue
                        ollama_locked = True

                # Get provider and make request
                provider = self._get_provider(provider_name)
                self._current_provider = provider
                self._current_name = provider_name

                logger.debug(f"Trying provider: {provider_name} ({provider.model})")

                response = await provider.complete(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )

                logger.info(f"Success with provider: {provider_name}")

                # Track failover state
                self._errors = errors
                if provider_name != self._primary:
                    self._failover_occurred = True
                    logger.info(
                        f"Failover: requested={self._primary}, "
                        f"actual={provider_name}"
                    )

                return response

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Provider {provider_name} failed: {error_msg}")
                errors.append((provider_name, error_msg))

                # Check if it's a 404 (Ollama not running)
                if "404" in error_msg and provider_name == "ollama":
                    logger.info("Ollama returned 404, likely not running")

            finally:
                # Release Ollama lock if we acquired it
                if ollama_locked and task_id:
                    await self._release_ollama_lock(task_id)
                    ollama_locked = False

        # All providers failed
        error_summary = "; ".join([f"{p}: {e}" for p, e in errors])
        raise Exception(f"All providers failed: {error_summary}")

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        task_id: str | None = None,
    ):
        """
        Stream completion with automatic failover.

        Tries each provider in the chain. Failover happens at connection time —
        once streaming starts, chunks are yielded directly.

        Yields:
            String chunks as they are generated.
        """
        errors = []
        ollama_locked = False
        self._failover_occurred = False
        self._errors = []

        for provider_name in self._chain:
            try:
                # Special handling for Ollama
                if provider_name == "ollama":
                    if not await self._check_ollama_available():
                        errors.append(("ollama", "unavailable or locked"))
                        continue
                    if task_id:
                        if not await self._acquire_ollama_lock(task_id):
                            errors.append(("ollama", "lock acquisition failed"))
                            continue
                        ollama_locked = True

                provider = self._get_provider(provider_name)
                self._current_provider = provider
                self._current_name = provider_name

                logger.debug(f"Trying stream: {provider_name} ({provider.model})")

                # Try to get the stream — failover happens here if connection fails
                chunk_count = 0
                async for chunk in provider.stream(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    chunk_count += 1
                    yield chunk

                # Stream completed successfully
                self._errors = errors
                if provider_name != self._primary:
                    self._failover_occurred = True
                    logger.info(
                        f"Stream failover: requested={self._primary}, "
                        f"actual={provider_name}"
                    )
                else:
                    logger.info(f"Stream success: {provider_name}")
                return

            except NotImplementedError:
                logger.info(f"{provider_name} does not support streaming, skipping")
                errors.append((provider_name, "streaming not supported"))
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Stream {provider_name} failed: {error_msg}")
                errors.append((provider_name, error_msg))
            finally:
                if ollama_locked and task_id:
                    await self._release_ollama_lock(task_id)
                    ollama_locked = False

        # All providers failed — raise
        error_summary = "; ".join([f"{p}: {e}" for p, e in errors])
        raise Exception(f"All stream providers failed: {error_summary}")


async def with_failover(
    func: Callable[..., T],
    provider_name: ProviderName = "ollama",
    enable_failover: bool = True,
    **kwargs,
) -> T:
    """
    Execute a function with provider failover support.

    If the function fails with the primary provider, retries with fallback providers.

    Args:
        func: Async function that uses an LLM provider
        provider_name: Primary provider
        enable_failover: If False, only use primary
        **kwargs: Additional arguments for the function

    Returns:
        Result from the function
    """
    failover_chain = DEFAULT_FAILOVER_CHAIN.copy()
    if provider_name in failover_chain:
        failover_chain.remove(provider_name)

    chain = [provider_name] + failover_chain if enable_failover else [provider_name]
    errors = []

    for pname in chain:
        try:
            return await func(provider=pname, **kwargs)
        except Exception as e:
            logger.warning(f"Function failed with {pname}: {e}")
            errors.append((pname, str(e)))

    error_summary = "; ".join([f"{p}: {e}" for p, e in errors])
    raise Exception(f"All providers failed: {error_summary}")


def get_available_provider(prefer_local: bool = True) -> ProviderName:
    """
    Get the best available provider (sync check).

    Args:
        prefer_local: If True, prefer Ollama if available

    Returns:
        Provider name that is available
    """
    config = get_config()

    # Check configured API keys
    available = []

    if config.effective_google_key:
        available.append("gemini")

    if config.effective_mistral_key:
        available.append("mistral")

    if config.anthropic_api_key:
        available.append("claude")

    # Ollama is always "available" (we'll check health at request time)
    if prefer_local:
        return "ollama"

    # Return first available external provider
    if available:
        return available[0]

    # Fallback to Ollama
    return "ollama"
