"""
Opik Tracing Integration

Provides decorators and utilities for tracing agent operations with Opik (Comet ML).

Configuration:
    OPIK_API_KEY: API key for Opik/Comet
    OPIK_WORKSPACE: Workspace name (e.g., "ocapistaine-dev")
    OPIK_PROJECT: Project name (e.g., "ocapistaine")

Structure:
    Project: ocapistaine (all agents share this)
    └── Traces: Full validation operations
        └── Spans: Individual steps (charter_validation, category_classification)
    └── Experiments: forseti-validation, forseti-classification, etc.
    └── Datasets: charter-evaluation (for optimization studio)
"""

import os
import functools
from contextlib import contextmanager
from typing import Any, Callable, TypeVar, Generator
from dataclasses import dataclass, field
from datetime import datetime

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class TraceContext:
    """Context for a single trace."""

    name: str
    input: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class DummySpan:
    """Dummy span for when Opik is disabled."""

    def update(self, **kwargs) -> None:
        """No-op update."""
        pass

    def end(self, **kwargs) -> None:
        """No-op end."""
        pass


class AgentTracer:
    """
    Tracer for agent operations using Opik.

    Provides automatic tracing of agent feature executions.
    Gracefully degrades if Opik is not configured.

    Usage:
        tracer = AgentTracer(project="ocapistaine")
        tracer.trace_validation(...)

    Experiments:
        tracer.start_experiment("forseti-validation")
        # ... run validations ...
        tracer.end_experiment()
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
        self._project = None
        self._current_experiment = None
        self._current_trace = None
        self._opik_module = None

        try:
            import opik

            key = api_key or os.getenv("OPIK_API_KEY")
            if not key:
                return

            ws = workspace or os.getenv("OPIK_WORKSPACE")
            proj = project or os.getenv("OPIK_PROJECT", "ocapistaine")

            # Configure Opik with workspace
            opik.configure(api_key=key, workspace=ws)

            self._client = opik.Opik(project_name=proj)
            self._project = proj
            self._opik_module = opik
            self.enabled = True

        except Exception as e:
            print(f"OPIK: Failed to initialize: {e}")

    @property
    def project(self) -> str | None:
        """Get current project name."""
        return self._project

    def start_experiment(
        self,
        name: str,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> str | None:
        """
        Start a new experiment for batch evaluation.

        Args:
            name: Experiment name (e.g., "forseti-validation-2026-01-21")
            description: Optional description
            metadata: Optional metadata dict

        Returns:
            Experiment ID if successful, None otherwise
        """
        if not self.enabled or not self._client:
            return None

        try:
            # Create timestamped experiment name if not unique
            exp_name = f"{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

            # Opik experiments are created via the evaluate() function
            # For manual experiments, we track via metadata
            self._current_experiment = {
                "name": exp_name,
                "description": description,
                "metadata": metadata or {},
                "started_at": datetime.now().isoformat(),
            }
            return exp_name
        except Exception as e:
            print(f"OPIK: Failed to start experiment: {e}")
            return None

    def end_experiment(self) -> None:
        """End the current experiment."""
        self._current_experiment = None

    def trace(
        self,
        name: str,
        input: dict,
        output: dict,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> str | None:
        """
        Record a trace.

        Args:
            name: Trace name (e.g., "charter_validation").
            input: Input data dict.
            output: Output data dict.
            metadata: Optional metadata dict.
            tags: Optional list of tags.

        Returns:
            Trace ID if successful, None otherwise
        """
        if not self.enabled or not self._client:
            return None

        try:
            # Add experiment info to metadata if active
            meta = metadata or {}
            if self._current_experiment:
                meta["experiment"] = self._current_experiment["name"]

            trace = self._client.trace(
                name=name,
                input=input,
                output=output,
                metadata=meta,
                tags=tags or [],
            )
            return trace.id if hasattr(trace, 'id') else None
        except Exception as e:
            print(f"OPIK: Failed to trace: {e}")
            return None

    @contextmanager
    def start_trace(
        self,
        name: str,
        input: dict | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> Generator[Any, None, None]:
        """
        Start a trace context for grouping spans.

        Usage:
            with tracer.start_trace("validate", input={...}) as trace:
                with tracer.span("step1", input={...}) as span:
                    ...
                    span.update(output={...})

        Args:
            name: Trace name
            input: Input data
            metadata: Optional metadata
            tags: Optional tags

        Yields:
            Trace object (or None if disabled)
        """
        if not self.enabled or not self._client:
            yield None
            return

        try:
            trace = self._client.trace(
                name=name,
                input=input or {},
                metadata=metadata or {},
                tags=tags or [],
            )
            self._current_trace = trace
            yield trace
        except Exception as e:
            print(f"OPIK: Failed to start trace: {e}")
            yield None
        finally:
            self._current_trace = None

    @contextmanager
    def span(
        self,
        name: str,
        input: dict | None = None,
        metadata: dict | None = None,
        span_type: str = "general",
    ) -> Generator[Any, None, None]:
        """
        Create a span within the current trace.

        Usage:
            with tracer.start_trace("validate") as trace:
                with tracer.span("charter_check", input={...}) as span:
                    result = do_validation()
                    span.update(output=result)

        Args:
            name: Span name
            input: Input data
            metadata: Optional metadata
            span_type: Type of span ("general", "llm", "tool")

        Yields:
            Span object with update() method (or DummySpan if disabled)
        """
        if not self.enabled or not self._current_trace:
            yield DummySpan()
            return

        try:
            span = self._current_trace.span(
                name=name,
                input=input or {},
                metadata=metadata or {},
                type=span_type,
            )
            yield span
        except Exception as e:
            print(f"OPIK: Failed to create span: {e}")
            yield DummySpan()

    def trace_validation(
        self,
        issue_data: dict,
        validation_result: dict,
        category_result: dict,
        agent_name: str = "forseti",
    ) -> str | None:
        """
        Trace a charter validation operation.

        Args:
            issue_data: Dict with title, body, category.
            validation_result: Dict with is_valid, violations, encouraged_aspects, etc.
            category_result: Dict with category, confidence, reasoning.
            agent_name: Name of the agent performing validation.

        Returns:
            Trace ID if successful, None otherwise
        """
        return self.trace(
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
                "agent": agent_name,
                "charter_confidence": validation_result.get("confidence"),
                "category_confidence": category_result.get("confidence"),
                "charter_reasoning": validation_result.get("reasoning"),
                "category_reasoning": category_result.get("reasoning"),
            },
            tags=[agent_name, "validation", "charter"],
        )

    def trace_feature(
        self,
        feature_name: str,
        input_data: dict,
        output_data: dict,
        agent_name: str = "forseti",
        metadata: dict | None = None,
    ) -> str | None:
        """
        Trace a feature execution.

        Args:
            feature_name: Name of the feature.
            input_data: Feature input.
            output_data: Feature output.
            agent_name: Name of the agent.
            metadata: Optional metadata.

        Returns:
            Trace ID if successful, None otherwise
        """
        meta = metadata or {}
        meta["agent"] = agent_name
        meta["feature"] = feature_name

        return self.trace(
            name=f"feature:{feature_name}",
            input=input_data,
            output=output_data,
            metadata=meta,
            tags=[agent_name, "feature", feature_name],
        )

    def create_dataset(
        self,
        name: str,
        description: str | None = None,
    ) -> Any | None:
        """
        Create or get a dataset for evaluation/optimization.

        Datasets can be used with Opik's optimization studio for:
        - Charter rule optimization
        - Prompt tuning
        - Model comparison

        Args:
            name: Dataset name (e.g., "charter-evaluation")
            description: Optional description

        Returns:
            Dataset object if successful, None otherwise
        """
        if not self.enabled or not self._client:
            return None

        try:
            dataset = self._client.get_or_create_dataset(
                name=name,
                description=description or f"Dataset for {name}",
            )
            return dataset
        except Exception as e:
            print(f"OPIK: Failed to create dataset: {e}")
            return None

    def add_to_dataset(
        self,
        dataset_name: str,
        items: list[dict],
    ) -> bool:
        """
        Add items to a dataset for evaluation.

        Args:
            dataset_name: Name of the dataset
            items: List of dicts with 'input' and optionally 'expected_output'

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self._client:
            return False

        try:
            dataset = self._client.get_or_create_dataset(name=dataset_name)
            dataset.insert(items)
            return True
        except Exception as e:
            print(f"OPIK: Failed to add to dataset: {e}")
            return False

    def log_feedback(
        self,
        trace_id: str,
        score: float,
        feedback_type: str = "user_rating",
        comment: str | None = None,
    ) -> bool:
        """
        Log feedback/score for a trace (for optimization studio).

        Args:
            trace_id: ID of the trace to score
            score: Score value (0.0 to 1.0)
            feedback_type: Type of feedback
            comment: Optional comment

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self._client:
            return False

        try:
            score_data = {"name": feedback_type, "value": score}
            if comment:
                score_data["reason"] = comment

            self._client.log_traces_feedback(
                trace_ids=[trace_id],
                scores=[score_data],
            )
            return True
        except Exception as e:
            print(f"OPIK: Failed to log feedback: {e}")
            return False


# Global tracer instance (lazy initialized)
_tracer: AgentTracer | None = None


def get_tracer(
    project: str | None = None,
    force_new: bool = False,
) -> AgentTracer:
    """
    Get or create the global tracer instance.

    Args:
        project: Optional project name override
        force_new: If True, create a new tracer even if one exists

    Returns:
        AgentTracer instance
    """
    global _tracer
    if _tracer is None or force_new:
        _tracer = AgentTracer(project=project)
    return _tracer


def trace_feature(feature_name: str, agent_name: str = "forseti") -> Callable[[F], F]:
    """
    Decorator to trace a feature execution.

    Usage:
        @trace_feature("charter_validation", agent_name="forseti")
        async def execute(self, provider, system_prompt, **kwargs):
            ...

    Args:
        feature_name: Name of the feature being traced.
        agent_name: Name of the agent.

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
                    agent_name=agent_name,
                )

                return result
            except Exception as e:
                tracer.trace_feature(
                    feature_name=feature_name,
                    input_data=input_data,
                    output_data={"error": str(e)},
                    agent_name=agent_name,
                    metadata={"status": "error"},
                )
                raise

        return wrapper  # type: ignore

    return decorator
