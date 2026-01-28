# app/logging/config.py
"""
Logging Configuration

Centralized configuration for all domain loggers.
Each domain has its own log file with rotation.
"""

import os
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Dict

# Log directory (project root / logs)
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Log format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# JSON format for structured logging (optional)
JSON_FORMAT = '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'

# Domain configuration
# Each domain maps to an architectural layer
DOMAINS: Dict[str, dict] = {
    "presentation": {
        "description": "Streamlit UI, FastAPI endpoints",
        "log_file": "presentation.log",
        "error_file": "presentation_errors.log",
        "level": logging.INFO,
    },
    "services": {
        "description": "Application layer services",
        "log_file": "services.log",
        "error_file": "services_errors.log",
        "level": logging.INFO,
    },
    "agents": {
        "description": "Business logic agents (RAG, crawler, eval)",
        "log_file": "agents.log",
        "error_file": "agents_errors.log",
        "level": logging.INFO,
    },
    "processors": {
        "description": "Business logic processors",
        "log_file": "processors.log",
        "error_file": "processors_errors.log",
        "level": logging.INFO,
    },
    "data": {
        "description": "Data access layer (Redis, vector store, files)",
        "log_file": "data.log",
        "error_file": "data_errors.log",
        "level": logging.INFO,
    },
    "providers": {
        "description": "LLM providers",
        "log_file": "providers.log",
        "error_file": "providers_errors.log",
        "level": logging.INFO,
    },
}

# Global logger cache
_loggers: Dict[str, logging.Logger] = {}


def setup_domain_logger(
    domain: str,
    level: int | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    console_output: bool = False,
) -> logging.Logger:
    """
    Set up a logger for a specific domain.

    Args:
        domain: Domain name (must be in DOMAINS)
        level: Log level (default from DOMAINS config)
        max_bytes: Max file size before rotation (default 10MB)
        backup_count: Number of backup files to keep
        console_output: Enable console output for development

    Returns:
        Configured logger for the domain
    """
    if domain not in DOMAINS:
        raise ValueError(f"Unknown domain: {domain}. Valid domains: {list(DOMAINS.keys())}")

    config = DOMAINS[domain]
    logger_name = f"ocapistaine.{domain}"
    logger = logging.getLogger(logger_name)

    # Don't add handlers if already configured
    if logger.handlers:
        return logger

    logger.setLevel(level or config["level"])
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # Main log file with size rotation
    main_handler = RotatingFileHandler(
        LOG_DIR / config["log_file"],
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    main_handler.setLevel(logging.DEBUG)
    main_handler.setFormatter(formatter)
    logger.addHandler(main_handler)

    # Error log file with time rotation (daily, keep 30 days)
    error_handler = TimedRotatingFileHandler(
        LOG_DIR / config["error_file"],
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    # Console handler (controlled by env var or parameter)
    env_console = os.getenv(f"{domain.upper()}_LOG_CONSOLE", "").lower() in ("1", "true", "yes")
    if console_output or env_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(domain: str) -> logging.Logger:
    """
    Get or create a logger for a domain.

    Args:
        domain: Domain name (presentation, services, agents, processors, data, providers)

    Returns:
        Logger instance for the domain
    """
    global _loggers

    if domain not in _loggers:
        _loggers[domain] = setup_domain_logger(domain)

    return _loggers[domain]


def setup_all_loggers(console_output: bool = False) -> Dict[str, logging.Logger]:
    """
    Initialize all domain loggers at application startup.

    Args:
        console_output: Enable console output for all loggers

    Returns:
        Dict of all configured loggers
    """
    for domain in DOMAINS:
        get_logger(domain)

    return _loggers


def get_child_logger(domain: str, component: str) -> logging.Logger:
    """
    Get a child logger for a specific component within a domain.

    Args:
        domain: Parent domain name
        component: Component name (e.g., "rag", "chat", "redis")

    Returns:
        Child logger that inherits domain configuration
    """
    parent = get_logger(domain)
    return parent.getChild(component)
