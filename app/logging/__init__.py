# app/logging/__init__.py
"""
OCapistaine - Centralized Logging System

Domain-based logging following Separation of Concerns principles.
Each architectural layer has its own logger and log file.

Domains:
- presentation: Streamlit UI, FastAPI endpoints
- services: Application layer (orchestrator, RAG, chat, document)
- agents: Business logic agents (RAG, crawler, evaluation)
- processors: Business logic processors (embeddings, parser, formatter)
- data: Data access layer (Redis, vector store, file storage)
- providers: LLM providers (Gemini, Claude, Mistral, Ollama)

Usage:
    from app.logging import get_logger, PresentationLogger, ServiceLogger

    # Simple usage
    logger = get_logger("services")
    logger.info("Service started")

    # Structured logging
    svc_logger = ServiceLogger("rag")
    svc_logger.log_request(user_id="abc", query="What is the budget?")
"""

from app.logging.config import (
    LOG_DIR,
    DOMAINS,
    setup_domain_logger,
    get_logger,
    setup_all_loggers,
)

from app.logging.domains import (
    PresentationLogger,
    ServiceLogger,
    AgentLogger,
    ProcessorLogger,
    DataLogger,
)

# Re-export provider logger for backwards compatibility
from app.providers.logging import (
    ProviderLogger,
    get_provider_logger,
)

__all__ = [
    # Configuration
    "LOG_DIR",
    "DOMAINS",
    "setup_domain_logger",
    "get_logger",
    "setup_all_loggers",
    # Domain loggers
    "PresentationLogger",
    "ServiceLogger",
    "AgentLogger",
    "ProcessorLogger",
    "DataLogger",
    # Provider logger (backwards compatible)
    "ProviderLogger",
    "get_provider_logger",
]
