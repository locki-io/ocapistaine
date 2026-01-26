# app/services/__init__.py
"""
OCapistaine - Application Services Layer

Initializes logging and provides service orchestration.
All domain loggers are configured at import time.

Usage:
    from app.services import (
        # Loggers
        presentation_logger,
        service_logger,
        agent_logger,
        processor_logger,
        data_logger,
        # Logger classes for custom components
        PresentationLogger,
        ServiceLogger,
        AgentLogger,
        ProcessorLogger,
        DataLogger,
    )

    # Use pre-configured loggers
    service_logger.log_request(user_id="abc", operation="chat")

    # Or create component-specific loggers
    rag_logger = ServiceLogger("rag")
    rag_logger.log_request(user_id="abc", operation="query", query="What is the budget?")
"""

import os
from app.logging import (
    setup_all_loggers,
    get_logger,
    PresentationLogger,
    ServiceLogger,
    AgentLogger,
    ProcessorLogger,
    DataLogger,
    ProviderLogger,
)

# =============================================================================
# Initialize all domain loggers at module import
# =============================================================================

# Check if console output is enabled (development mode)
_console_output = os.getenv("LOG_CONSOLE", "").lower() in ("1", "true", "yes")

# Initialize all loggers
_loggers = setup_all_loggers(console_output=_console_output)

# =============================================================================
# Pre-configured domain loggers for common use
# =============================================================================

# Presentation layer (Streamlit, FastAPI)
presentation_logger = PresentationLogger("main")

# Services layer (application services)
service_logger = ServiceLogger("main")

# Agents layer (business logic agents)
agent_logger = AgentLogger("main")

# Processors layer (business logic processors)
processor_logger = ProcessorLogger("main")

# Data access layer
data_logger = DataLogger("main")

# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Pre-configured loggers
    "presentation_logger",
    "service_logger",
    "agent_logger",
    "processor_logger",
    "data_logger",
    # Logger classes for custom components
    "PresentationLogger",
    "ServiceLogger",
    "AgentLogger",
    "ProcessorLogger",
    "DataLogger",
    "ProviderLogger",
    # Utility
    "get_logger",
]
