"""
Opik Tracing Integration

Provides decorators and utilities for tracing agent operations with Opik (Comet ML).
"""

import os
import functools
from typing import Any, Callable, TypeVar
from dataclasses import dataclass, field

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class TraceContext:
    """Context for a single trace."""

    name: str
    input: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class AgentTracer:
    """
    Tracer for agent operations using Opik.

    Provides automatic tracing of agent feature executions.
    Gracefully degrades if Opik is not configured.
    """

    def __init__(
        self,
        api_key: str | None = None,
        workspace: str | None = None,
        project: str | None = None,
    ):
        """
        Initialize the tracer.

        Args:
            api_key: Opik API key (falls back to OPIK_API_KEY env var).
            workspace: Opik workspace (falls back to OPIK_WORKSPACE env var).
            project: Opik project name (falls back to OPIK_PROJECT env var).
        """
        self.enabled = False
        self._client = None

        try:
            import opik

            key = api_key or os.getenv("OPIK_API_KEY")
            if not key:
                return

            ws = workspace or os.getenv("OPIK_WORKSPACE")
            opik.configure(api_key=key, workspace=ws)

            self._client = opik.Opik()
            self._project = project or os.getenv("OPIK_PROJECT", "forseti")
            self.enabled = True
        except Exception:
            pass

    def trace(
        self,
        name: str,
        input: dict,
        output: dict,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """
        Record a trace.

        Args:
            name: Trace name (e.g., "charter_validation").
            input: Input data dict.
            output: Output data dict.
            metadata: Optional metadata dict.
            tags: Optional list of tags.
        """
        if not self.enabled or not self._client:
            return

        try:
            self._client.trace(
                name=name,
                input=input,
                output=output,
                metadata=metadata or {},
                tags=tags or [],
            )
        except Exception:
            pass

    def trace_validation(
        self,
        issue_data: dict,
        validation_result: dict,
        category_result: dict,
    ) -> None:
        """
        Trace a charter validation operation.

        Compatibility method matching the original OpikTracer.trace_validation.

        Args:
            issue_data: Dict with title, body, category.
            validation_result: Dict with is_valid, violations, encouraged_aspects, etc.
            category_result: Dict with category, confidence, reasoning.
        """
        self.trace(
            name="charter_validation",
            input={
                "title": issue_data.get("title"),
                "body": issue_data.get("body"),
                "original_category": issue_data.get("category"),
            },
            output={
                "is_valid": validation_result.get("is_valid"),
                "violations": validation_result.get("violations"),
                "encouraged_aspects": validation_result.get("encouraged_aspects"),
                "category": category_result.get("category"),
            },
            metadata={
                "charter_confidence": validation_result.get("confidence"),
                "category_confidence": category_result.get("confidence"),
                "charter_reasoning": validation_result.get("reasoning"),
                "category_reasoning": category_result.get("reasoning"),
            },
            tags=["forseti", "validation"],
        )

    def trace_feature(
        self,
        feature_name: str,
        input_data: dict,
        output_data: dict,
        metadata: dict | None = None,
    ) -> None:
        """
        Trace a feature execution.

        Args:
            feature_name: Name of the feature.
            input_data: Feature input.
            output_data: Feature output.
            metadata: Optional metadata.
        """
        self.trace(
            name=f"feature_{feature_name}",
            input=input_data,
            output=output_data,
            metadata=metadata or {},
            tags=["forseti", "feature", feature_name],
        )


# Global tracer instance (lazy initialized)
_tracer: AgentTracer | None = None


def get_tracer() -> AgentTracer:
    """Get or create the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = AgentTracer()
    return _tracer


def trace_feature(feature_name: str) -> Callable[[F], F]:
    """
    Decorator to trace a feature execution.

    Usage:
        @trace_feature("charter_validation")
        async def execute(self, provider, system_prompt, **kwargs):
            ...

    Args:
        feature_name: Name of the feature being traced.

    Returns:
        Decorated function that traces input/output.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()

            # Capture input (filter out provider and system_prompt)
            input_data = {
                k: v
                for k, v in kwargs.items()
                if k not in ("provider", "system_prompt")
            }

            try:
                result = await func(*args, **kwargs)

                # Capture output
                if hasattr(result, "to_dict"):
                    output_data = result.to_dict()
                elif hasattr(result, "model_dump"):
                    output_data = result.model_dump()
                elif isinstance(result, dict):
                    output_data = result
                else:
                    output_data = {"result": str(result)}

                tracer.trace_feature(
                    feature_name=feature_name,
                    input_data=input_data,
                    output_data=output_data,
                )

                return result
            except Exception as e:
                tracer.trace_feature(
                    feature_name=feature_name,
                    input_data=input_data,
                    output_data={"error": str(e)},
                    metadata={"status": "error"},
                )
                raise

        return wrapper  # type: ignore

    return decorator
