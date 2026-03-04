"""
Provider Health Check

Single startup check that verifies Ollama models and cloud API key availability.
Results are cached module-level and consumed by /status endpoint and sidebar filtering.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TypedDict

import httpx

from app.providers.config import OLLAMA_MODELS, get_config
from app.services.logging.domains import ServiceLogger

_logger = ServiceLogger("providers")


# ---- Types ----

class OllamaStatus(TypedDict):
    running: bool
    available_models: list[str]
    unavailable_models: list[str]


class ProviderHealthReport(TypedDict):
    ollama: OllamaStatus
    cloud: dict[str, bool]
    checked_at: str


# ---- Module-level cache ----

_status: ProviderHealthReport | None = None


def get_provider_status() -> ProviderHealthReport | None:
    """Read-only accessor for the cached health report."""
    return _status


# ---- Ollama check ----

async def _check_ollama() -> OllamaStatus:
    """Check which configured Ollama models are actually pulled.

    Makes a single GET to /api/tags and matches against OLLAMA_MODELS keys.
    """
    config = get_config()
    host = config.ollama_host.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{host}/api/tags")
            resp.raise_for_status()

        data = resp.json()
        pulled_names: set[str] = set()
        for model in data.get("models", []):
            name = model.get("name", "")
            pulled_names.add(name)
            # Also add without :latest suffix for flexible matching
            if ":" in name:
                pulled_names.add(name.rsplit(":", 1)[0])

        available: list[str] = []
        unavailable: list[str] = []

        for key, model_info in OLLAMA_MODELS.items():
            model_name = model_info["name"]
            # Check exact match, or without tag suffix
            base_name = model_name.rsplit(":", 1)[0] if ":" in model_name else model_name
            if model_name in pulled_names or base_name in pulled_names:
                available.append(key)
            else:
                unavailable.append(key)

        return OllamaStatus(
            running=True,
            available_models=available,
            unavailable_models=unavailable,
        )

    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
        _logger.warning("OLLAMA_UNREACHABLE", host=host, error=str(exc)[:100])
        all_keys = list(OLLAMA_MODELS.keys())
        return OllamaStatus(
            running=False,
            available_models=[],
            unavailable_models=all_keys,
        )


# ---- Cloud provider check (env vars only, no network) ----

def _check_cloud_providers() -> dict[str, bool]:
    config = get_config()
    return {
        "gemini": bool(config.effective_google_key),
        "claude": bool(config.anthropic_api_key),
        "mistral": bool(config.effective_mistral_key),
        "openai": bool(config.openai_api_key),
    }


# ---- Main entry point ----

async def check_providers() -> ProviderHealthReport:
    """Run all provider health checks once and cache the result.

    Safe to call multiple times; result is cached module-level.
    """
    global _status

    try:
        ollama = await asyncio.wait_for(_check_ollama(), timeout=10)
    except asyncio.TimeoutError:
        _logger.warning("OLLAMA_TIMEOUT", detail="Health check exceeded 10s")
        all_keys = list(OLLAMA_MODELS.keys())
        ollama = OllamaStatus(
            running=False,
            available_models=[],
            unavailable_models=all_keys,
        )

    cloud = _check_cloud_providers()

    report = ProviderHealthReport(
        ollama=ollama,
        cloud=cloud,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )

    _status = report

    # Log summary
    _logger.info(
        "HEALTH_CHECK",
        ollama_running=ollama["running"],
        ollama_available=len(ollama["available_models"]),
        ollama_unavailable=len(ollama["unavailable_models"]),
        cloud_configured=", ".join(k for k, v in cloud.items() if v) or "none",
    )

    return report
