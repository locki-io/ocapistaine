"""
Provider Configuration

Pydantic settings for all LLM providers with environment variable support.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class ProviderConfig(BaseSettings):
    """Configuration for all LLM providers."""

    # Default provider selection
    default_provider: str = Field(default="gemini", alias="DEFAULT_PROVIDER")

    # Google Gemini
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")
    gemini_rate_limit: float = Field(default=12.0, alias="GEMINI_RATE_LIMIT")

    # Anthropic Claude
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    claude_model: str = Field(
        default="claude-3-haiku-20240307", alias="CLAUDE_MODEL"
    )

    # Mistral AI
    mistral_api_key: str | None = Field(default=None, alias="MISTRAL_API_KEY")
    mistral_model: str = Field(default="mistral-small-latest", alias="MISTRAL_MODEL")

    # Local Ollama
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="mistral:latest", alias="OLLAMA_MODEL")

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
