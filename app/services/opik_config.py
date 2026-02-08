"""
Opik Evaluation Configuration

Stores Opik evaluation settings in Redis.
These settings control the LLM used for Opik's built-in metrics (LLM judges).

Default: OpenAI gpt-4o-mini

Settings:
- app:opik:judge:provider - LLM provider for Opik judges (openai, anthropic)
- app:opik:judge:model - Model name (gpt-4o-mini, gpt-4o, etc.)
- app:opik:judge:api_key_env - Environment variable name for API key
"""

import os
import redis
from typing import Optional
from dotenv import load_dotenv

from app.services.logging import get_logger
from app.data.redis_client import _get_redis_config, APP_KEY_PREFIX

load_dotenv()

logger = get_logger("services")

# Default Opik judge configuration
DEFAULT_OPIK_JUDGE = {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key_env": "OPENAI_API_KEY",
}

# Redis keys (with app: prefix)
KEY_JUDGE_PROVIDER = f"{APP_KEY_PREFIX}opik:judge:provider"
KEY_JUDGE_MODEL = f"{APP_KEY_PREFIX}opik:judge:model"
KEY_JUDGE_API_KEY_ENV = f"{APP_KEY_PREFIX}opik:judge:api_key_env"


def _get_redis() -> redis.Redis:
    """Get Redis connection for Opik config."""
    host, port, password, use_ssl = _get_redis_config()
    redis_db = int(os.getenv("REDIS_DB", "0"))

    return redis.Redis(
        host=host,
        port=port,
        password=password,
        db=redis_db,
        decode_responses=True,
        ssl=use_ssl,
        ssl_cert_reqs=None if use_ssl else None,
    )


def get_opik_judge_config() -> dict:
    """
    Get current Opik judge LLM configuration.

    Returns:
        dict with provider, model, api_key_env
    """
    try:
        r = _get_redis()

        config = {
            "provider": r.get(KEY_JUDGE_PROVIDER) or DEFAULT_OPIK_JUDGE["provider"],
            "model": r.get(KEY_JUDGE_MODEL) or DEFAULT_OPIK_JUDGE["model"],
            "api_key_env": r.get(KEY_JUDGE_API_KEY_ENV) or DEFAULT_OPIK_JUDGE["api_key_env"],
        }

        # Check if API key is available
        api_key = os.getenv(config["api_key_env"])
        config["api_key_configured"] = bool(api_key)

        return config

    except Exception as e:
        logger.warning(f"Failed to get Opik config from Redis: {e}")
        return {
            **DEFAULT_OPIK_JUDGE,
            "api_key_configured": bool(os.getenv(DEFAULT_OPIK_JUDGE["api_key_env"])),
        }


def set_opik_judge_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key_env: Optional[str] = None,
) -> dict:
    """
    Update Opik judge LLM configuration.

    Args:
        provider: LLM provider (openai, anthropic)
        model: Model name
        api_key_env: Environment variable name for API key

    Returns:
        Updated config dict
    """
    try:
        r = _get_redis()

        if provider:
            r.set(KEY_JUDGE_PROVIDER, provider)
            logger.info(f"Set Opik judge provider: {provider}")

        if model:
            r.set(KEY_JUDGE_MODEL, model)
            logger.info(f"Set Opik judge model: {model}")

        if api_key_env:
            r.set(KEY_JUDGE_API_KEY_ENV, api_key_env)
            logger.info(f"Set Opik judge API key env: {api_key_env}")

        return get_opik_judge_config()

    except Exception as e:
        logger.error(f"Failed to set Opik config: {e}")
        raise


def reset_opik_judge_config() -> dict:
    """
    Reset Opik judge config to defaults.

    Returns:
        Default config dict
    """
    try:
        r = _get_redis()
        r.delete(KEY_JUDGE_PROVIDER, KEY_JUDGE_MODEL, KEY_JUDGE_API_KEY_ENV)
        logger.info("Reset Opik judge config to defaults")
        return get_opik_judge_config()

    except Exception as e:
        logger.error(f"Failed to reset Opik config: {e}")
        raise


def configure_opik_environment():
    """
    Configure environment variables for Opik evaluation.

    This sets up the OpenAI API key for Opik's LLM judges
    based on the stored configuration.
    """
    config = get_opik_judge_config()

    # Get API key from configured env var
    api_key = os.getenv(config["api_key_env"])

    if api_key:
        # Set OPENAI_API_KEY for Opik (it uses OpenAI by default)
        if config["provider"] == "openai":
            os.environ["OPENAI_API_KEY"] = api_key
            logger.debug(f"Configured OpenAI API key for Opik from {config['api_key_env']}")

        # Set model preference
        os.environ["OPIK_LLM_MODEL"] = config["model"]
        logger.debug(f"Set Opik LLM model: {config['model']}")

        return True
    else:
        logger.warning(f"API key not found in env var: {config['api_key_env']}")
        return False


# Available Opik judge models
AVAILABLE_JUDGE_MODELS = {
    "openai": [
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini (recommended)", "cost": "low"},
        {"id": "gpt-4o", "name": "GPT-4o", "cost": "medium"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "cost": "high"},
    ],
    "anthropic": [
        {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku", "cost": "low"},
        {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet", "cost": "medium"},
    ],
}


def list_available_judge_models() -> dict:
    """List available models for Opik judges."""
    return AVAILABLE_JUDGE_MODELS
