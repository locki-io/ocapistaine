# app/logging/__init__.py
"""
DEPRECATED: This module has been moved to app.services.logging

This file exists for backwards compatibility only.
Please update imports to use:
    from app.services.logging import ...
"""

import warnings

warnings.warn(
    "app.logging is deprecated. Use app.services.logging instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from the new location
from app.services.logging import (
    LOG_DIR,
    DOMAINS,
    setup_domain_logger,
    get_logger,
    setup_all_loggers,
    get_child_logger,
    BaseLogger,
    PresentationLogger,
    ServiceLogger,
    AgentLogger,
    ProcessorLogger,
    DataLogger,
    TaskLogger,
    ProviderLogger,
    get_provider_logger,
)

__all__ = [
    "LOG_DIR",
    "DOMAINS",
    "setup_domain_logger",
    "get_logger",
    "setup_all_loggers",
    "get_child_logger",
    "BaseLogger",
    "PresentationLogger",
    "ServiceLogger",
    "AgentLogger",
    "ProcessorLogger",
    "DataLogger",
    "TaskLogger",
    "ProviderLogger",
    "get_provider_logger",
]
