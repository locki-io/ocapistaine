"""
LLM Provider Factory

Exports all providers and provides a factory function for instantiation.
"""

from typing import Literal

from .base import LLMProvider, Message, CompletionResponse
from .config import ProviderConfig, get_config, GEMINI_MODELS
from .logging import get_provider_logger, ProviderLogger, get_logger
from .gemini import GeminiProvider
from .claude import ClaudeProvider
from .mistral import MistralProvider
from .ollama import OllamaProvider


__all__ = [
    "LLMProvider",
    "Message",
    "CompletionResponse",
    "ProviderConfig",
    "get_config",
    "GEMINI_MODELS",
    "GeminiProvider",
    "ClaudeProvider",
    "MistralProvider",
    "OllamaProvider",
    "get_provider",
    "get_provider_logger",
    "ProviderLogger",
    "get_logger",
]


ProviderName = Literal["gemini", "claude", "mistral", "ollama"]

# Provider registry
_PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "claude": ClaudeProvider,
    "mistral": MistralProvider,
    "ollama": OllamaProvider,
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
        name: Provider name ("gemini", "claude", "mistral", "ollama").
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
