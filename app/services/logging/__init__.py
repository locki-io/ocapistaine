# app/services/logging/__init__.py
"""
OCapistaine - Centralized Logging Service

Domain-based logging following Separation of Concerns principles.
Each architectural layer has its own logger and log file.

Domains:
- presentation: Streamlit UI, FastAPI endpoints
- services: Application layer (orchestrator, RAG, chat, document)
- agents: Business logic agents (RAG, crawler, evaluation)
- processors: Business logic processors (embeddings, parser, formatter)
- data: Data access layer (Redis, vector store, file storage)
- providers: LLM providers (Gemini, Claude, Mistral, Ollama)
- tasks: Scheduled tasks and background jobs

Usage:
    from app.services.logging import get_logger, TaskLogger, ServiceLogger

    # Simple usage
    logger = get_logger("services")
    logger.info("Service started")

    # Structured task logging
    task_logger = TaskLogger("task_contributions_analysis")
    task_logger.log_start(task_id="abc123", date_string="20260203")
    task_logger.log_completed(status="success", validated=10, approved=8)

    # Structured service logging
    svc_logger = ServiceLogger("rag")
    svc_logger.log_request(user_id="abc", query="What is the budget?")
"""

from app.services.logging.config import (
    LOG_DIR,
    TASK_LOG_DIR,
    DOMAINS,
    setup_domain_logger,
    get_logger,
    setup_all_loggers,
    get_child_logger,
)

from app.services.logging.domains import (
    BaseLogger,
    PresentationLogger,
    ServiceLogger,
    AgentLogger,
    ProcessorLogger,
    DataLogger,
    TaskLogger,
)

# Re-export provider logger for backwards compatibility
from app.providers.logging import (
    ProviderLogger,
    get_provider_logger,
)

__all__ = [
    # Configuration
    "LOG_DIR",
    "TASK_LOG_DIR",
    "DOMAINS",
    "setup_domain_logger",
    "get_logger",
    "setup_all_loggers",
    "get_child_logger",
    # Domain loggers
    "BaseLogger",
    "PresentationLogger",
    "ServiceLogger",
    "AgentLogger",
    "ProcessorLogger",
    "DataLogger",
    "TaskLogger",
    # Provider logger (backwards compatible)
    "ProviderLogger",
    "get_provider_logger",
]
