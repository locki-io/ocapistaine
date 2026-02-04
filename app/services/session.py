# app/services/session.py
"""
Session Settings Storage

Persists user session settings (provider, model, language) in Redis db5.
Allows settings to be shared across different parts of the application.

Key format: session:settings:{user_id}
"""

import json
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

from app.data.redis_client import redis_connection
from app.services import AgentLogger

_logger = AgentLogger("session_settings")


# TTL for session settings (24 hours)
SESSION_SETTINGS_TTL = 86400


@dataclass
class SessionSettings:
    """User session settings."""

    user_id: str
    provider: str = "ollama"
    model: str = "mistral"
    language: str = "fr"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSettings":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class SessionSettingsKey:
    """Redis key patterns for session settings."""

    SETTINGS = "session:settings:{user_id}"

    @staticmethod
    def settings(user_id: str) -> str:
        """Get key for user session settings."""
        return f"session:settings:{user_id}"


def save_session_settings(user_id: str, provider: str, model: str, language: str = "fr") -> bool:
    """
    Save session settings to Redis.

    Args:
        user_id: User identifier
        provider: LLM provider name
        model: Model key/name
        language: Language code

    Returns:
        True if successful
    """
    try:
        settings = SessionSettings(
            user_id=user_id,
            provider=provider,
            model=model,
            language=language,
        )

        key = SessionSettingsKey.settings(user_id)

        with redis_connection() as r:
            r.setex(key, SESSION_SETTINGS_TTL, json.dumps(settings.to_dict()))

        _logger.info(
            "SETTINGS_SAVED",
            user_id=user_id[:8],
            provider=provider,
            model=model,
        )
        return True

    except Exception as e:
        _logger.error("SETTINGS_SAVE_ERROR", user_id=user_id[:8], error=str(e)[:100])
        return False


def get_session_settings(user_id: str) -> Optional[SessionSettings]:
    """
    Get session settings from Redis.

    Args:
        user_id: User identifier

    Returns:
        SessionSettings if found, None otherwise
    """
    try:
        key = SessionSettingsKey.settings(user_id)

        with redis_connection() as r:
            data = r.get(key)

        if data:
            return SessionSettings.from_dict(json.loads(data))

        return None

    except Exception as e:
        _logger.error("SETTINGS_GET_ERROR", user_id=user_id[:8], error=str(e)[:100])
        return None


def get_session_provider(user_id: str) -> str:
    """
    Get the provider from session settings.

    Args:
        user_id: User identifier

    Returns:
        Provider name (defaults to "ollama")
    """
    settings = get_session_settings(user_id)
    return settings.provider if settings else "ollama"


def get_session_model(user_id: str) -> str:
    """
    Get the model from session settings.

    Args:
        user_id: User identifier

    Returns:
        Model key/name (defaults to "mistral")
    """
    settings = get_session_settings(user_id)
    return settings.model if settings else "mistral"


def get_full_model_id(provider: str, model_key: str) -> str:
    """
    Convert provider + model key to full model ID.

    Args:
        provider: Provider name (ollama, gemini, claude, mistral)
        model_key: Short model key

    Returns:
        Full model identifier for the provider
    """
    model_maps = {
        "ollama": {
            "mistral": "mistral:latest",
            "llama3.2": "llama3.2:latest",
            "orca-mini": "orca-mini:latest",
        },
        "gemini": {
            "flash-lite": "gemini-2.0-flash-lite",
            "flash": "gemini-2.5-flash",
            "pro": "gemini-2.5-pro-exp",
        },
        "claude": {
            "haiku": "claude-3-haiku-20240307",
            "sonnet": "claude-3-5-sonnet-20241022",
        },
        "mistral": {
            "small": "mistral-small-latest",
            "medium": "mistral-medium-latest",
        },
    }

    provider_models = model_maps.get(provider, {})
    return provider_models.get(model_key, model_key)


def get_session_full_model_id(user_id: str) -> str:
    """
    Get the full model ID from session settings.

    Args:
        user_id: User identifier

    Returns:
        Full model identifier
    """
    settings = get_session_settings(user_id)
    if settings:
        return get_full_model_id(settings.provider, settings.model)
    return "mistral:latest"


# Global default user ID for background tasks
_default_user_id: Optional[str] = None


def set_default_user_id(user_id: str) -> None:
    """Set the default user ID for background tasks."""
    global _default_user_id
    _default_user_id = user_id


def get_default_user_id() -> Optional[str]:
    """Get the default user ID for background tasks."""
    return _default_user_id


def get_current_provider() -> str:
    """
    Get current provider from default user settings or fallback.

    For use in background tasks and non-UI contexts.

    Returns:
        Provider name
    """
    if _default_user_id:
        return get_session_provider(_default_user_id)
    return "ollama"


def get_current_model() -> str:
    """
    Get current model from default user settings or fallback.

    For use in background tasks and non-UI contexts.

    Returns:
        Model key
    """
    if _default_user_id:
        return get_session_model(_default_user_id)
    return "mistral"


def get_provider_for_tracing() -> Dict[str, str]:
    """
    Get provider info for Opik tracing metadata.

    Returns:
        Dict with provider and model info for trace metadata
    """
    provider = get_current_provider()
    model = get_current_model()
    full_model = get_full_model_id(provider, model)

    return {
        "provider": provider,
        "model_key": model,
        "model_id": full_model,
    }
