"""
Provider Configuration

Pydantic settings for all LLM providers with environment variable support.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


# Gemini free tier models (2026-01)
GEMINI_MODELS = {
    "flash-lite": "gemini-2.5-flash-lite",  # Cheapest/fastest, great for high-volume or lightweight tasks
    "flash": "gemini-2.5-flash",  # Best balance: fast + capable (most popular free default in 2026)
    "pro": "gemini-2.5-pro",  # Strongest reasoning/coding among free models
    # Optional extras if you want previews or aliases
    "flash-preview": "gemini-2.5-flash-preview",  # Sometimes used for latest experimental tweaks
    "pro-preview": "gemini-2.5-pro-preview",  # If you need bleeding-edge Pro features
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
    "deepseek-r1:14b": {
        "name": "deepseek-r1:14b",
        "description": "DeepSeek R1 14B - Better reasoning",
        "ram_gb": 10,
        "use_case": "Complex reasoning, higher quality",
    },
}


class ProviderConfig(BaseSettings):
    """Configuration for all LLM providers."""

    # Default provider selection
    default_provider: str = Field(default="gemini", alias="DEFAULT_PROVIDER")

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
    mistral_model: str = Field(default="mistral-small-latest", alias="MISTRAL_MODEL")

    # Local Ollama
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="deepseek-r1:7b", alias="OLLAMA_MODEL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def effective_google_key(self) -> str | None:
        """Return the effective Google API key (GOOGLE_API_KEY or GEMINI_API_KEY)."""
        return self.google_api_key or self.gemini_api_key


# Singleton instance
_config: ProviderConfig | None = None


def get_config() -> ProviderConfig:
    """Get or create the singleton config instance."""
    global _config
    if _config is None:
        _config = ProviderConfig()
    return _config
