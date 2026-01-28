# app/logging/domains.py
"""
Domain-Specific Structured Loggers

Each logger provides structured logging methods for its architectural layer.
Follows Separation of Concerns principles from the architecture.
"""

from datetime import datetime
from typing import Any
import logging

from app.logging.config import get_logger, get_child_logger


class BaseLogger:
    """Base class for domain loggers with common functionality."""

    domain: str = "base"

    def __init__(self, component: str):
        """
        Initialize a domain logger for a specific component.

        Args:
            component: Component name within the domain
        """
        self.component = component
        self._logger = get_child_logger(self.domain, component)

    def _format_parts(self, **kwargs) -> str:
        """Format key-value pairs for log message."""
        parts = [f"{k}={v}" for k, v in kwargs.items() if v is not None]
        return " | ".join(parts)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with optional structured data."""
        if kwargs:
            message = f"{message} | {self._format_parts(**kwargs)}"
        self._logger.debug(message)

    def info(self, message: str, **kwargs) -> None:
        """Log info message with optional structured data."""
        if kwargs:
            message = f"{message} | {self._format_parts(**kwargs)}"
        self._logger.info(message)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with optional structured data."""
        if kwargs:
            message = f"{message} | {self._format_parts(**kwargs)}"
        self._logger.warning(message)

    def error(self, message: str, **kwargs) -> None:
        """Log error message with optional structured data."""
        if kwargs:
            message = f"{message} | {self._format_parts(**kwargs)}"
        self._logger.error(message)

    def exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback."""
        if kwargs:
            message = f"{message} | {self._format_parts(**kwargs)}"
        self._logger.exception(message)


# =============================================================================
# Presentation Layer Logger
# =============================================================================


class PresentationLogger(BaseLogger):
    """
    Logger for Presentation Layer (Streamlit UI, FastAPI).

    Components: streamlit, fastapi, webhooks
    """

    domain = "presentation"

    def log_page_view(
        self,
        page: str,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Log a page view event."""
        self.info(
            "PAGE_VIEW",
            page=page,
            user_id=user_id[:8] if user_id else None,
            session=session_id[:8] if session_id else None,
        )

    def log_user_action(
        self,
        action: str,
        user_id: str | None = None,
        details: str | None = None,
    ) -> None:
        """Log a user action (button click, form submit, etc.)."""
        self.info(
            "USER_ACTION",
            action=action,
            user_id=user_id[:8] if user_id else None,
            details=details,
        )

    def log_api_request(
        self,
        method: str,
        path: str,
        user_id: str | None = None,
        status_code: int | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Log an API request."""
        self.info(
            "API_REQUEST",
            method=method,
            path=path,
            user_id=user_id[:8] if user_id else None,
            status=status_code,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
        )

    def log_api_error(
        self,
        method: str,
        path: str,
        error: str,
        status_code: int = 500,
    ) -> None:
        """Log an API error."""
        self.error(
            "API_ERROR",
            method=method,
            path=path,
            status=status_code,
            error=error,
        )

    def log_webhook(
        self,
        source: str,
        event_type: str,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Log webhook event (N8N, GitHub, etc.)."""
        level = self.info if success else self.error
        level(
            "WEBHOOK",
            source=source,
            event=event_type,
            success=success,
            error=error,
        )


# =============================================================================
# Services Layer Logger
# =============================================================================


class ServiceLogger(BaseLogger):
    """
    Logger for Application Layer Services.

    Components: orchestrator, rag, chat, document
    """

    domain = "services"

    def log_request(
        self,
        user_id: str,
        operation: str,
        query: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        """Log a service request."""
        self.info(
            "REQUEST",
            operation=operation,
            user_id=user_id[:8] if user_id else None,
            thread=thread_id[:8] if thread_id else None,
            query=query[:50] if query else None,
        )

    def log_response(
        self,
        user_id: str,
        operation: str,
        success: bool = True,
        latency_ms: float | None = None,
        result_count: int | None = None,
    ) -> None:
        """Log a service response."""
        self.info(
            "RESPONSE",
            operation=operation,
            user_id=user_id[:8] if user_id else None,
            success=success,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
            results=result_count,
        )

    def log_cache_hit(
        self,
        cache_type: str,
        key: str,
        hit: bool = True,
    ) -> None:
        """Log cache hit/miss."""
        self.debug(
            "CACHE",
            type=cache_type,
            key=key[:20],
            hit=hit,
        )

    def log_service_error(
        self,
        operation: str,
        error: str,
        user_id: str | None = None,
        recoverable: bool = True,
    ) -> None:
        """Log a service error."""
        self.error(
            "SERVICE_ERROR",
            operation=operation,
            user_id=user_id[:8] if user_id else None,
            error=error,
            recoverable=recoverable,
        )


# =============================================================================
# Agents Layer Logger
# =============================================================================


class AgentLogger(BaseLogger):
    """
    Logger for Business Logic Agents.

    Components: rag, crawler, evaluation, forseti
    """

    domain = "agents"

    def log_agent_start(
        self,
        task: str,
        input_data: str | None = None,
    ) -> None:
        """Log agent task start."""
        self.info(
            "AGENT_START",
            task=task,
            input=input_data[:50] if input_data else None,
        )

    def log_agent_complete(
        self,
        task: str,
        success: bool = True,
        latency_ms: float | None = None,
        output_summary: str | None = None,
    ) -> None:
        """Log agent task completion."""
        level = self.info if success else self.warning
        level(
            "AGENT_COMPLETE",
            task=task,
            success=success,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
            output=output_summary[:50] if output_summary else None,
        )

    def log_retrieval(
        self,
        query: str,
        num_results: int,
        top_score: float | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Log RAG retrieval step."""
        self.info(
            "RETRIEVAL",
            query=query[:50],
            results=num_results,
            top_score=f"{top_score:.3f}" if top_score else None,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
        )

    def log_generation(
        self,
        model: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Log LLM generation step."""
        self.info(
            "GENERATION",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
        )

    def log_evaluation(
        self,
        metric: str,
        score: float,
        threshold: float | None = None,
        passed: bool | None = None,
    ) -> None:
        """Log evaluation metric (Opik)."""
        self.info(
            "EVALUATION",
            metric=metric,
            score=f"{score:.3f}",
            threshold=f"{threshold:.3f}" if threshold else None,
            passed=passed,
        )

    def log_validation(
        self,
        validator: str,
        is_valid: bool,
        violations: list[str] | None = None,
        confidence: float | None = None,
    ) -> None:
        """Log validation result (Forseti)."""
        level = self.info if is_valid else self.warning
        level(
            "VALIDATION",
            validator=validator,
            valid=is_valid,
            violations=len(violations) if violations else 0,
            confidence=f"{confidence:.2f}" if confidence else None,
        )


# =============================================================================
# Processors Layer Logger
# =============================================================================


class ProcessorLogger(BaseLogger):
    """
    Logger for Business Logic Processors.

    Components: embeddings, parser, formatter
    """

    domain = "processors"

    def log_process_start(
        self,
        processor: str,
        input_type: str,
        input_size: int | None = None,
        **kwargs
    ) -> None:
        """Log processing start."""
        self.info(
            "PROCESS_START",
            processor=processor,
            input_type=input_type,
            input_size=input_size,
            **kwargs
        )

    def log_process_complete(
        self,
        processor: str,
        output_type: str,
        output_size: int | None = None,
        latency_ms: float | None = None,
        **kwargs
    ) -> None:
        """Log processing completion."""
        self.info(
            "PROCESS_COMPLETE",
            processor=processor,
            output_type=output_type,
            output_size=output_size,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
            **kwargs
        )

    def log_embedding(
        self,
        model: str,
        num_texts: int,
        dimensions: int | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Log embedding generation."""
        self.info(
            "EMBEDDING",
            model=model,
            texts=num_texts,
            dimensions=dimensions,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
        )

    def log_parse(
        self,
        source_type: str,
        source_path: str,
        success: bool = True,
        pages: int | None = None,
        chars: int | None = None,
    ) -> None:
        """Log document parsing."""
        level = self.info if success else self.error
        level(
            "PARSE",
            type=source_type,
            path=source_path[-50:],
            success=success,
            pages=pages,
            chars=chars,
        )


# =============================================================================
# Data Access Layer Logger
# =============================================================================


class DataLogger(BaseLogger):
    """
    Logger for Data Access Layer.

    Components: redis, vector_store, file_storage
    """

    domain = "data"

    def log_connection(
        self,
        store: str,
        status: str,
        host: str | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Log data store connection."""
        level = self.info if status == "connected" else self.error
        level(
            "CONNECTION",
            store=store,
            status=status,
            host=host,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
        )

    def log_operation(
        self,
        store: str,
        operation: str,
        key: str | None = None,
        success: bool = True,
        latency_ms: float | None = None,
    ) -> None:
        """Log data operation (read/write)."""
        self.debug(
            "OPERATION",
            store=store,
            op=operation,
            key=key[:30] if key else None,
            success=success,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
        )

    def log_redis_command(
        self,
        command: str,
        key: str,
        success: bool = True,
        ttl: int | None = None,
    ) -> None:
        """Log Redis command."""
        self.debug(
            "REDIS",
            cmd=command,
            key=key[:30],
            success=success,
            ttl=ttl,
        )

    def log_vector_search(
        self,
        collection: str,
        num_results: int,
        latency_ms: float | None = None,
    ) -> None:
        """Log vector store search."""
        self.info(
            "VECTOR_SEARCH",
            collection=collection,
            results=num_results,
            latency_ms=f"{latency_ms:.0f}" if latency_ms else None,
        )

    def log_file_operation(
        self,
        operation: str,
        path: str,
        size_bytes: int | None = None,
        success: bool = True,
    ) -> None:
        """Log file storage operation."""
        level = self.debug if success else self.error
        level(
            "FILE",
            op=operation,
            path=path[-50:],
            size=size_bytes,
            success=success,
        )
