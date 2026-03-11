"""
LLM Provider Factory

Exports all providers and provides a factory function for instantiation.
"""

from .base import LLMProvider, Message, CompletionResponse
from .config import (
    ProviderConfig,
    get_config,
    ProviderName,
    # Model ID mappings
    GEMINI_MODELS,
    CLAUDE_MODELS,
    MISTRAL_MODELS,
    OLLAMA_MODELS,
    OLLAMA_MODEL_IDS,
    OPENAI_MODELS,
    # UI config
    PROVIDER_UI_CONFIG,
    # Recommended models per use case
    RECOMMENDED_MODELS,
    # Functions
    get_model_id,
    get_default_model,
    list_model_keys,
    get_recommended_model,
)
from .logging import get_provider_logger, ProviderLogger, get_logger
from .gemini import GeminiProvider
from .claude import ClaudeProvider
from .mistral import MistralProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .failover import (
    ProviderWithFailover,
    with_failover,
    get_available_provider,
    DEFAULT_FAILOVER_CHAIN,
)
from .health import check_providers, get_provider_status


__all__ = [
    "LLMProvider",
    "Message",
    "CompletionResponse",
    "ProviderConfig",
    "get_config",
    "ProviderName",
    # Model ID mappings
    "GEMINI_MODELS",
    "CLAUDE_MODELS",
    "MISTRAL_MODELS",
    "OLLAMA_MODELS",
    "OLLAMA_MODEL_IDS",
    "OPENAI_MODELS",
    # UI config
    "PROVIDER_UI_CONFIG",
    # Recommended models
    "RECOMMENDED_MODELS",
    # Model resolution functions
    "get_model_id",
    "get_default_model",
    "list_model_keys",
    "get_recommended_model",
    # Provider classes
    "GeminiProvider",
    "ClaudeProvider",
    "MistralProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "get_provider",
    "get_provider_logger",
    "ProviderLogger",
    "get_logger",
    # Failover support
    "ProviderWithFailover",
    "with_failover",
    "get_available_provider",
    "DEFAULT_FAILOVER_CHAIN",
    # Health check
    "check_providers",
    "get_provider_status",
]


# Provider registry
_PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "claude": ClaudeProvider,
    "mistral": MistralProvider,
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
}

# Cached provider instances
_instances: dict[str, LLMProvider] = {}


def get_provider(
    name: ProviderName | None = None,
    cache: bool = True,
    **kwargs,
) -> LLMProvider:
    """
    Factory function to get an LLM provider instance.

    Args:
        name: Provider name ("gemini", "claude", "mistral", "ollama", "openai").
              If None, uses DEFAULT_PROVIDER from environment.
        cache: If True, return cached instance if available.
        **kwargs: Additional arguments passed to provider constructor.

    Returns:
        LLMProvider instance.

    Raises:
        ValueError: If provider name is not recognized.

    Example:
        >>> provider = get_provider("gemini")
        >>> response = await provider.complete([Message("user", "Hello")])
    """
    config = get_config()
    provider_name = name or config.default_provider

    if provider_name not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Available: {', '.join(_PROVIDERS.keys())}"
        )

    # Return cached instance if available and no custom kwargs
    cache_key = provider_name
    if cache and not kwargs and cache_key in _instances:
        return _instances[cache_key]

    # Create new instance
    provider_class = _PROVIDERS[provider_name]
    instance = provider_class(**kwargs)

    # Cache it if no custom kwargs
    if cache and not kwargs:
        _instances[cache_key] = instance

    return instance


def clear_provider_cache():
    """Clear all cached provider instances."""
    global _instances
    _instances = {}


def list_providers() -> list[str]:
    """List all available provider names."""
    return list(_PROVIDERS.keys())
