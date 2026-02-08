"""
Provider Configuration

Pydantic settings for all LLM providers with environment variable support.
Single source of truth for model configurations across the application.
"""

from typing import Literal
from pydantic_settings import BaseSettings
from pydantic import Field


# =============================================================================
# PROVIDER TYPE
# =============================================================================
ProviderName = Literal["gemini", "claude", "mistral", "ollama", "openai"]


# =============================================================================
# MODEL ID MAPPINGS (key -> full model ID)
# =============================================================================

# Gemini free tier models (2026-01)
GEMINI_MODELS = {
    "flash-lite": "gemini-2.5-flash-lite",  # Cheapest/fastest (~1000 req/day)
    "flash": "gemini-2.5-flash",  # Best balance (~20 req/day)
    "pro": "gemini-2.5-pro",  # Strongest reasoning (~25 req/day)
    "flash-preview": "gemini-2.5-flash-preview",  # Experimental
    "pro-preview": "gemini-2.5-pro-preview",  # Bleeding-edge
}

# Claude models (Anthropic)
CLAUDE_MODELS = {
    "haiku": "claude-3-haiku-20240307",  # Fast, cheap
    "sonnet": "claude-3-5-sonnet-20241022",  # Balanced
    "opus": "claude-3-opus-20240229",  # Most capable
}

# OpenAI models
OPENAI_MODELS = {
    "gpt-4o-mini": "gpt-4o-mini",  # Fast, cheap, good quality
    "gpt-4o": "gpt-4o",  # Best balance
    "gpt-4-turbo": "gpt-4-turbo",  # Previous generation
    "gpt-3.5-turbo": "gpt-3.5-turbo",  # Legacy, cheapest
}

# Mistral API models
MISTRAL_MODELS = {
    "tiny": "mistral-tiny-latest",  # Ultra-light
    "small": "mistral-small-latest",  # Good French, fast
    "medium": "mistral-medium-latest",  # Balanced
    "large": "mistral-large-latest",  # Most capable
}

# Ollama local models - sorted by resource usage (lightest first)
OLLAMA_MODELS = {
    # Ultra-light models (< 4GB RAM)
    "qwen3:4b": {
        "name": "qwen3:4b",
        "description": "Qwen 3 4B - Ultra-light, good for simple tasks",
        "ram_gb": 3,
        "use_case": "Simple classification, low-resource environments",
    },
    "qwen3-vl:4b": {
        "name": "qwen3-vl:4b",
        "description": "Qwen 3 Vision-Language 4B - Multimodal ultra-light",
        "ram_gb": 3,
        "use_case": "Vision tasks, document analysis, low-resource",
    },
    # Light models (4-8GB RAM)
    "deepseek-r1:7b": {
        "name": "deepseek-r1:7b",
        "description": "DeepSeek R1 7B - Efficient reasoning model",
        "ram_gb": 5,
        "use_case": "Reasoning tasks, charter validation, low CPU usage",
    },
    "mistral:7b": {
        "name": "mistral:7b",
        "description": "Mistral 7B - Balanced performance",
        "ram_gb": 6,
        "use_case": "General purpose, good quality/speed balance",
    },
    "mistral:latest": {
        "name": "mistral:latest",
        "description": "Mistral latest - Default Mistral model",
        "ram_gb": 6,
        "use_case": "General purpose fallback",
    },
    # Heavier models (8-16GB RAM)
    "llama3:8b": {
        "name": "llama3:8b",
        "description": "Llama 3 8B - Meta's latest",
        "ram_gb": 8,
        "use_case": "High quality outputs, more resources available",
    },
    "llama3.2:latest": {
        "name": "llama3.2:latest",
        "description": "Llama 3.2 - Latest Llama",
        "ram_gb": 8,
        "use_case": "General purpose, good quality",
    },
    "deepseek-r1:14b": {
        "name": "deepseek-r1:14b",
        "description": "DeepSeek R1 14B - Better reasoning",
        "ram_gb": 10,
        "use_case": "Complex reasoning, higher quality",
    },
    "orca-mini:latest": {
        "name": "orca-mini:latest",
        "description": "Orca Mini - Lightweight, fast",
        "ram_gb": 4,
        "use_case": "Quick tasks, low-resource",
    },
}

# Simple key -> model ID for Ollama (for UI dropdowns)
OLLAMA_MODEL_IDS = {k: v["name"] for k, v in OLLAMA_MODELS.items()}


# =============================================================================
# PROVIDER UI CONFIGURATION
# =============================================================================
PROVIDER_UI_CONFIG = {
    "gemini": {
        "name_key": "provider_google_gemini",
        "models": {
            "flash-lite": "gemini-2.5-flash-lite (~1000 req/day)",
            "flash": "gemini-2.5-flash (~20 req/day)",
        },
        "default": "flash-lite",
    },
    "claude": {
        "name_key": "provider_anthropic_claude",
        "models": {
            "haiku": "claude-3-haiku (fast, cheap)",
            "sonnet": "claude-3.5-sonnet (balanced)",
        },
        "default": "haiku",
    },
    "mistral": {
        "name_key": "provider_mistral_ai",
        "models": {
            "small": "mistral-small-latest",
            "medium": "mistral-medium-latest",
        },
        "default": "small",
    },
    "ollama": {
        "name_key": "provider_ollama",
        "models": {
            "deepseek-r1:7b": "DeepSeek R1 7B (reasoning)",
            "mistral:7b": "Mistral 7B (balanced)",
            "mistral:latest": "Mistral latest",
            "llama3.2:latest": "Llama 3.2 latest",
            "orca-mini:latest": "Orca Mini (light)",
        },
        "default": "deepseek-r1:7b",
    },
    "openai": {
        "name_key": "provider_openai",
        "models": {
            "gpt-4o-mini": "GPT-4o Mini (fast, cheap)",
            "gpt-4o": "GPT-4o (best balance)",
            "gpt-3.5-turbo": "GPT-3.5 Turbo (legacy)",
        },
        "default": "gpt-4o-mini",
    },
}


# =============================================================================
# MODEL ID RESOLUTION
# =============================================================================
def get_model_id(provider: str, model_key: str) -> str:
    """
    Get the full model ID for a provider and model key.

    This is the SINGLE function to use for resolving model keys to IDs.
    Used by sidebar.py, session.py, and other modules.

    Args:
        provider: Provider name (gemini, claude, mistral, ollama, openai)
        model_key: Short model key (e.g., "flash", "haiku", "small")

    Returns:
        Full model identifier for the provider API
    """
    if provider == "gemini":
        return GEMINI_MODELS.get(model_key, "gemini-2.5-flash-lite")
    elif provider == "claude":
        return CLAUDE_MODELS.get(model_key, "claude-3-haiku-20240307")
    elif provider == "mistral":
        return MISTRAL_MODELS.get(model_key, "mistral-small-latest")
    elif provider == "openai":
        return OPENAI_MODELS.get(model_key, "gpt-4o-mini")
    elif provider == "ollama":
        # Ollama keys can be the model ID directly or a key
        if model_key in OLLAMA_MODELS:
            return OLLAMA_MODELS[model_key]["name"]
        return model_key  # Assume it's already a model ID
    return model_key  # Fallback: return as-is


def get_default_model(provider: str) -> str:
    """Get the default model key for a provider."""
    if provider in PROVIDER_UI_CONFIG:
        return PROVIDER_UI_CONFIG[provider]["default"]
    return "mistral:latest"


def list_model_keys(provider: str) -> list[str]:
    """List available model keys for a provider."""
    if provider in PROVIDER_UI_CONFIG:
        return list(PROVIDER_UI_CONFIG[provider]["models"].keys())
    return []


# =============================================================================
# RECOMMENDED MODELS PER USE CASE
# =============================================================================
# Use case -> provider -> model key (for tasks requiring specific capabilities)
RECOMMENDED_MODELS = {
    # Field Input: theme extraction, contribution generation (needs reasoning)
    "field_input": {
        "gemini": "flash",
        "claude": "sonnet",
        "mistral": "small",
        "ollama": "deepseek-r1:7b",
        "openai": "gpt-4o-mini",
    },
    # Charter validation (Forseti)
    "charter_validation": {
        "gemini": "flash",
        "claude": "sonnet",
        "mistral": "small",
        "ollama": "deepseek-r1:7b",
        "openai": "gpt-4o-mini",
    },
    # Mockup mutations (fast generation)
    "mockup_mutations": {
        "gemini": "flash-lite",
        "claude": "haiku",
        "mistral": "small",
        "ollama": "mistral:7b",
        "openai": "gpt-4o-mini",
    },
    # Default fallback
    "default": {
        "gemini": "flash-lite",
        "claude": "haiku",
        "mistral": "small",
        "ollama": "deepseek-r1:7b",
        "openai": "gpt-4o-mini",
    },
}


def get_recommended_model(
    provider: str,
    use_case: str = "default",
    model_override: str | None = None,
) -> str:
    """
    Get the recommended model ID for a provider and use case.

    This handles the model override pattern used throughout the app:
    - If model_override is provided, use it (resolve key to ID if needed)
    - Otherwise, use the recommended model for the use case

    Args:
        provider: Provider name (gemini, claude, mistral, ollama)
        use_case: Use case name (field_input, charter_validation, etc.)
        model_override: Optional explicit model override (key or full ID)

    Returns:
        Full model ID ready for the provider API
    """
    if model_override:
        # User provided explicit model - resolve it
        return get_model_id(provider, model_override)

    # Get recommended key for use case
    use_case_models = RECOMMENDED_MODELS.get(use_case, RECOMMENDED_MODELS["default"])
    model_key = use_case_models.get(provider, get_default_model(provider))

    # Resolve key to full ID
    return get_model_id(provider, model_key)


class ProviderConfig(BaseSettings):
    """Configuration for all LLM providers."""

    # Default provider selection (ollama for local-first development)
    default_provider: str = Field(default="ollama", alias="DEFAULT_PROVIDER")

    # Google Gemini
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash-lite", alias="GEMINI_MODEL")
    gemini_rate_limit: float = Field(
        default=1.0, alias="GEMINI_RATE_LIMIT"
    )  # flash-lite allows ~1000/day

    # Anthropic Claude
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    claude_model: str = Field(default="claude-3-haiku-20240307", alias="CLAUDE_MODEL")

    # Mistral AI
    mistral_api_key: str | None = Field(default=None, alias="MISTRAL_API_KEY")
    mistral_studio_api_key: str | None = Field(default=None, alias="MISTRAL_STUDIO_API_KEY")
    mistral_model: str = Field(default="mistral-small-latest", alias="MISTRAL_MODEL")

    # Local Ollama
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="deepseek-r1:7b", alias="OLLAMA_MODEL")

    # OpenAI
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_rate_limit: float = Field(default=0.5, alias="OPENAI_RATE_LIMIT")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def effective_google_key(self) -> str | None:
        """Return the effective Google API key (GOOGLE_API_KEY or GEMINI_API_KEY)."""
        return self.google_api_key or self.gemini_api_key

    @property
    def effective_mistral_key(self) -> str | None:
        """Return the effective Mistral API key (MISTRAL_API_KEY or MISTRAL_STUDIO_API_KEY)."""
        return self.mistral_api_key or self.mistral_studio_api_key


# Singleton instance
_config: ProviderConfig | None = None


def get_config() -> ProviderConfig:
    """Get or create the singleton config instance."""
    global _config
    if _config is None:
        _config = ProviderConfig()
    return _config
