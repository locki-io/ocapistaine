"""
Provider Logging

Centralized logging for LLM providers with file rotation.

Logs:
- API calls (provider, model, tokens)
- Errors (rate limits, quota exhausted, API errors)
- Costs tracking (when available)

Log files:
- logs/providers.log (main log, rotated daily)
- logs/providers_errors.log (errors only)
"""

import os
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime


# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Log format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_provider_logger(
    name: str = "providers",
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Set up a logger with file rotation for providers.

    Args:
        name: Logger name
        level: Log level (default INFO)
        max_bytes: Max file size before rotation (default 10MB)
        backup_count: Number of backup files to keep

    Returns:
        Configured logger
    """
    logger = logging.getLogger(f"ocapistaine.{name}")

    # Don't add handlers if already configured
    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # Main log file with size rotation
    main_handler = RotatingFileHandler(
        LOG_DIR / f"{name}.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    main_handler.setLevel(logging.DEBUG)
    main_handler.setFormatter(formatter)
    logger.addHandler(main_handler)

    # Error log file (errors only, time rotation daily)
    error_handler = TimedRotatingFileHandler(
        LOG_DIR / f"{name}_errors.log",
        when="midnight",
        interval=1,
        backupCount=30,  # Keep 30 days of error logs
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    # Console handler for development (only warnings and above)
    if os.getenv("PROVIDER_LOG_CONSOLE", "").lower() in ("1", "true", "yes"):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# Global provider logger
_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    """Get the global provider logger."""
    global _logger
    if _logger is None:
        _logger = setup_provider_logger()
    return _logger


class ProviderLogger:
    """
    Structured logging helper for provider operations.

    Usage:
        logger = ProviderLogger("gemini")
        logger.log_request(model="gemini-2.0-flash", tokens=100)
        logger.log_response(model="gemini-2.0-flash", tokens=500, latency_ms=1200)
        logger.log_error("RATE_LIMIT", "Quota exceeded", retry_after=30)
    """

    def __init__(self, provider_name: str):
        self.provider = provider_name
        self._logger = get_logger()

    def log_request(
        self,
        model: str,
        input_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> None:
        """Log an API request."""
        parts = [f"provider={self.provider}", f"model={model}"]
        if input_tokens:
            parts.append(f"input_tokens={input_tokens}")
        if temperature is not None:
            parts.append(f"temp={temperature}")
        if json_mode:
            parts.append("json_mode=true")

        self._logger.info(f"REQUEST | {' | '.join(parts)}")

    def log_response(
        self,
        model: str,
        output_tokens: int | None = None,
        latency_ms: float | None = None,
        cached: bool = False,
    ) -> None:
        """Log an API response."""
        parts = [f"provider={self.provider}", f"model={model}"]
        if output_tokens:
            parts.append(f"output_tokens={output_tokens}")
        if latency_ms:
            parts.append(f"latency_ms={latency_ms:.0f}")
        if cached:
            parts.append("cached=true")

        self._logger.info(f"RESPONSE | {' | '.join(parts)}")

    def log_error(
        self,
        error_type: str,
        message: str,
        model: str | None = None,
        retry_after: float | None = None,
        details: dict | None = None,
    ) -> None:
        """
        Log an API error.

        Error types:
        - RATE_LIMIT: Rate limit exceeded
        - QUOTA_EXHAUSTED: API quota/credits exhausted
        - AUTH_ERROR: Authentication failed
        - API_ERROR: General API error
        - TIMEOUT: Request timeout
        - PARSE_ERROR: Response parsing failed
        """
        parts = [f"provider={self.provider}", f"type={error_type}"]
        if model:
            parts.append(f"model={model}")
        if retry_after:
            parts.append(f"retry_after={retry_after}s")

        self._logger.error(f"ERROR | {' | '.join(parts)} | {message}")

        if details:
            self._logger.debug(f"ERROR_DETAILS | {details}")

    def log_quota_warning(
        self,
        model: str,
        remaining: int | None = None,
        limit: int | None = None,
        reset_time: str | None = None,
    ) -> None:
        """Log a quota warning (low credits, approaching limit)."""
        parts = [f"provider={self.provider}", f"model={model}"]
        if remaining is not None:
            parts.append(f"remaining={remaining}")
        if limit is not None:
            parts.append(f"limit={limit}")
        if reset_time:
            parts.append(f"reset={reset_time}")

        self._logger.warning(f"QUOTA | {' | '.join(parts)}")

    def log_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float | None = None,
    ) -> None:
        """Log cost tracking (when available)."""
        parts = [
            f"provider={self.provider}",
            f"model={model}",
            f"in={input_tokens}",
            f"out={output_tokens}",
        ]
        if cost_usd is not None:
            parts.append(f"cost=${cost_usd:.6f}")

        self._logger.info(f"COST | {' | '.join(parts)}")


# Convenience function to get a logger for a specific provider
def get_provider_logger(provider_name: str) -> ProviderLogger:
    """Get a ProviderLogger for a specific provider."""
    return ProviderLogger(provider_name)
