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
        task_logger,
        # Logger classes for custom components
        PresentationLogger,
        ServiceLogger,
        AgentLogger,
        ProcessorLogger,
        DataLogger,
        TaskLogger,
        # Translations
        _,
        get_language,
        set_language,
        language_selector,
    )

    # Use pre-configured loggers
    service_logger.log_request(user_id="abc", operation="chat")

    # Or create component-specific loggers
    rag_logger = ServiceLogger("rag")
    rag_logger.log_request(user_id="abc", operation="query", query="What is the budget?")

    # Task-specific logging
    from app.services import TaskLogger
    logger = TaskLogger("task_contributions_analysis")
    logger.log_start(task_id="abc", date_string="20260203")

    # Translations
    text = _("app_title")  # Get translated text
    lang = get_language()  # "fr" or "en"
"""

import os
from app.services.logging import (
    setup_all_loggers,
    get_logger,
    PresentationLogger,
    ServiceLogger,
    AgentLogger,
    ProcessorLogger,
    DataLogger,
    TaskLogger,
    ProviderLogger,
)
from app.services.translations import (
    _,
    get_language,
    set_language,
    language_selector,
    LANGUAGES,
)
from app.services.session import (
    SessionSettings,
    save_session_settings,
    get_session_settings,
    get_session_provider,
    get_session_model,
    get_full_model_id,
    get_session_full_model_id,
    get_current_provider,
    get_current_model,
    get_provider_for_tracing,
    set_default_user_id,
    get_default_user_id,
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

# Task execution logger (for scheduler tasks)
task_logger = TaskLogger("scheduler")

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
    "task_logger",
    # Logger classes for custom components
    "PresentationLogger",
    "ServiceLogger",
    "AgentLogger",
    "ProcessorLogger",
    "DataLogger",
    "TaskLogger",
    "ProviderLogger",
    # Utility
    "get_logger",
    # Translations
    "_",
    "get_language",
    "set_language",
    "language_selector",
    "LANGUAGES",
    # Session settings
    "SessionSettings",
    "save_session_settings",
    "get_session_settings",
    "get_session_provider",
    "get_session_model",
    "get_full_model_id",
    "get_session_full_model_id",
    "get_current_provider",
    "get_current_model",
    "get_provider_for_tracing",
    "set_default_user_id",
    "get_default_user_id",
]
