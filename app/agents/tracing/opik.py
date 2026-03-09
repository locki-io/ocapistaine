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

Provider Labeling:
    All traces and spans include provider information from session settings:
    - provider: The LLM provider name (ollama, gemini, claude, mistral)
    - model_key: Short model identifier
    - model_id: Full model identifier
"""

import os
import functools
from contextlib import contextmanager
from typing import Any, Callable, TypeVar, Generator, Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.services.logging import AgentLogger

F = TypeVar("F", bound=Callable[..., Any])

logger = AgentLogger("opik")


def _get_provider_metadata() -> dict:
    """
    Get provider metadata for tracing.

    Returns provider info from session settings or defaults.
    """
    try:
        from app.services.session import get_provider_for_tracing

        return get_provider_for_tracing()
    except Exception:
        return {
            "provider": "unknown",
            "model_key": "unknown",
            "model_id": "unknown",
        }


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
        self._current_thread_id: str | None = None
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
            logger.warning(f"OPIK: Failed to initialize: {e}")

    @property
    def project(self) -> str | None:
        """Get current project name."""
        return self._project

    def start_experiment(
        self,
        name: str,
        description: str | None = None,
        metadata: dict | None = None,
        provider_info: dict | None = None,
    ) -> str | None:
        """
        Start a new experiment for batch evaluation.

        Args:
            name: Experiment name (e.g., "forseti-validation-2026-01-21")
            description: Optional description
            metadata: Optional metadata dict
            provider_info: Optional provider info (auto-populated from session if None)

        Returns:
            Experiment ID if successful, None otherwise
        """
        if not self.enabled or not self._client:
            return None

        try:
            # Create timestamped experiment name if not unique
            exp_name = f"{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

            # Get provider info
            prov_info = provider_info or _get_provider_metadata()

            # Merge metadata with provider info
            exp_metadata = metadata or {}
            exp_metadata.update(prov_info)

            # Opik experiments are created via the evaluate() function
            # For manual experiments, we track via metadata
            self._current_experiment = {
                "name": exp_name,
                "description": description,
                "metadata": exp_metadata,
                "started_at": datetime.now().isoformat(),
            }
            return exp_name
        except Exception as e:
            logger.error(f"OPIK: Failed to start experiment: {e}")
            return None

    def end_experiment(self) -> None:
        """End the current experiment."""
        self._current_experiment = None

    @contextmanager
    def start_thread(self, thread_id: str) -> Generator[str, None, None]:
        """
        Start a thread scope — all traces created within inherit the thread_id.

        Opik threads group traces into a conversation view, so each user
        session becomes a thread with multiple traces (one per question).

        Usage:
            with tracer.start_thread(session_id) as tid:
                with tracer.start_trace("rag_chat", ...) as trace:
                    ...  # trace is automatically part of the thread

        Args:
            thread_id: Unique thread identifier (typically the session ID)

        Yields:
            The thread_id being used
        """
        previous = self._current_thread_id
        self._current_thread_id = thread_id
        try:
            yield thread_id
        finally:
            self._current_thread_id = previous

    def trace(
        self,
        name: str,
        input: dict,
        output: dict,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        provider_info: dict | None = None,
        thread_id: str | None = None,
    ) -> str | None:
        """
        Record a trace.

        Args:
            name: Trace name (e.g., "charter_validation").
            input: Input data dict.
            output: Output data dict.
            metadata: Optional metadata dict.
            tags: Optional list of tags.
            provider_info: Optional provider info (auto-populated from session if None).
            thread_id: Optional thread ID to group traces into a conversation.

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

            # Add provider info to metadata (from session or explicit)
            if provider_info:
                meta.update(provider_info)
            else:
                meta.update(_get_provider_metadata())

            # Add provider to tags for filtering
            trace_tags = list(tags or [])
            if meta.get("provider") and meta["provider"] not in trace_tags:
                trace_tags.append(meta["provider"])

            # Use explicit thread_id or inherit from start_thread() scope
            effective_thread_id = thread_id or self._current_thread_id

            kwargs = dict(
                name=name,
                input=input,
                output=output,
                metadata=meta,
                tags=trace_tags,
            )
            if effective_thread_id:
                kwargs["thread_id"] = effective_thread_id

            trace = self._client.trace(**kwargs)
            return trace.id if hasattr(trace, 'id') else None
        except Exception as e:
            logger.error(f"OPIK: Failed to trace: {e}")
            return None

    @contextmanager
    def start_trace(
        self,
        name: str,
        input: dict | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        provider_info: dict | None = None,
        thread_id: str | None = None,
    ) -> Generator[Any, None, None]:
        """
        Start a trace context for grouping spans.

        Usage:
            with tracer.start_trace("validate", input={...}, thread_id="abc") as trace:
                with tracer.span("step1", input={...}) as span:
                    ...
                    span.update(output={...})

        Args:
            name: Trace name
            input: Input data
            metadata: Optional metadata
            tags: Optional tags
            provider_info: Optional provider info (auto-populated from session if None)
            thread_id: Optional thread ID to group traces into a conversation

        Yields:
            Trace object (or None if disabled)
        """
        if not self.enabled or not self._client:
            yield None
            return

        trace = None
        try:
            # Add provider info to metadata
            meta = metadata or {}
            if provider_info:
                meta.update(provider_info)
            else:
                meta.update(_get_provider_metadata())

            # Add provider to tags
            trace_tags = list(tags or [])
            if meta.get("provider") and meta["provider"] not in trace_tags:
                trace_tags.append(meta["provider"])

            # Use explicit thread_id or inherit from start_thread() scope
            effective_thread_id = thread_id or self._current_thread_id

            kwargs = dict(
                name=name,
                input=input or {},
                metadata=meta,
                tags=trace_tags,
            )
            if effective_thread_id:
                kwargs["thread_id"] = effective_thread_id

            trace = self._client.trace(**kwargs)
            self._current_trace = trace
        except Exception as e:
            logger.error(f"OPIK: Failed to start trace: {e}")
        try:
            yield trace
        finally:
            self._current_trace = None

    @contextmanager
    def span(
        self,
        name: str,
        input: dict | None = None,
        metadata: dict | None = None,
        span_type: str = "general",
        provider_info: dict | None = None,
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
            provider_info: Optional provider info (auto-populated from session if None)

        Yields:
            Span object with update() method (or DummySpan if disabled)
        """
        if not self.enabled or not self._current_trace:
            yield DummySpan()
            return

        s = DummySpan()
        try:
            # Add provider info to metadata
            meta = metadata or {}
            if provider_info:
                meta.update(provider_info)
            else:
                meta.update(_get_provider_metadata())

            s = self._current_trace.span(
                name=name,
                input=input or {},
                metadata=meta,
                type=span_type,
            )
        except Exception as e:
            logger.error(f"OPIK: Failed to create span: {e}")
        yield s

    def trace_validation(
        self,
        issue_data: dict,
        validation_result: dict,
        category_result: dict,
        agent_name: str = "forseti",
        provider_info: dict | None = None,
    ) -> str | None:
        """
        Trace a charter validation operation.

        Args:
            issue_data: Dict with title, body, category.
            validation_result: Dict with is_valid, violations, encouraged_aspects, etc.
            category_result: Dict with category, confidence, reasoning.
            agent_name: Name of the agent performing validation.
            provider_info: Optional provider info (auto-populated from session if None).

        Returns:
            Trace ID if successful, None otherwise
        """
        # Get provider info if not provided
        prov_info = provider_info or _get_provider_metadata()

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
            provider_info=prov_info,
        )

    def trace_feature(
        self,
        feature_name: str,
        input_data: dict,
        output_data: dict,
        agent_name: str = "forseti",
        metadata: dict | None = None,
        provider_info: dict | None = None,
    ) -> str | None:
        """
        Trace a feature execution.

        Args:
            feature_name: Name of the feature.
            input_data: Feature input.
            output_data: Feature output.
            agent_name: Name of the agent.
            metadata: Optional metadata.
            provider_info: Optional provider info (auto-populated from session if None).

        Returns:
            Trace ID if successful, None otherwise
        """
        meta = metadata or {}
        meta["agent"] = agent_name
        meta["feature"] = feature_name

        # Get provider info if not provided
        prov_info = provider_info or _get_provider_metadata()

        return self.trace(
            name=f"feature:{feature_name}",
            input=input_data,
            output=output_data,
            metadata=meta,
            tags=[agent_name, "feature", feature_name],
            provider_info=prov_info,
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
            logger.error(f"OPIK: Failed to create dataset: {e}")
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
            logger.error(f"OPIK: Failed to add to dataset: {e}")
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
            # FeedbackScoreDict format: id is INSIDE the score dict
            score_data = {
                "id": trace_id,  # trace_id goes in the dict
                "name": feedback_type,
                "value": score,
            }
            if comment:
                score_data["reason"] = comment

            # Correct method name: log_traces_feedback_scores (not log_traces_feedback)
            self._client.log_traces_feedback_scores(scores=[score_data])
            return True
        except Exception as e:
            logger.error(f"OPIK: Failed to log trace feedback: {e}")
            return False

    def log_span_feedback(
        self,
        span_id: str,
        score: float,
        feedback_type: str = "Correctness",
        comment: str | None = None,
    ) -> bool:
        """
        Log feedback/score for a span (for Opik-native querying and optimization).

        Args:
            span_id: ID of the span to score
            score: Score value (0.0 to 1.0)
            feedback_type: Type of feedback (default: "Correctness")
            comment: Optional comment

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self._client:
            return False

        try:
            # FeedbackScoreDict format: id is INSIDE the score dict
            score_data = {
                "id": span_id,  # span_id goes in the dict
                "name": feedback_type,
                "value": score,
            }
            if comment:
                score_data["reason"] = comment

            # Correct method name: log_spans_feedback_scores (not log_spans_feedback)
            self._client.log_spans_feedback_scores(scores=[score_data])
            logger.debug(f"OPIK: Logged {feedback_type}={score} to span {span_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"OPIK: Failed to log span feedback: {e}")
            return False

    def search_traces(
        self,
        filter_string: str | None = None,
        max_results: int = 100,
    ) -> list[dict]:
        """
        Search traces by filter criteria.

        Uses Opik Query Language (OQL) for filtering.

        Args:
            filter_string: OQL filter (e.g., "feedback_scores.validation_confidence < 0.5")
            max_results: Maximum number of results

        Returns:
            List of trace dicts with id, input, output, feedback_scores, etc.

        Example:
            traces = tracer.search_traces(
                filter_string="feedback_scores.validation_confidence < 0.5",
                max_results=50,
            )
        """
        if not self.enabled or not self._client:
            return []

        try:
            traces = self._client.search_traces(
                project_name=self._project,
                filter_string=filter_string,
                max_results=max_results,
            )
            # Convert to list of dicts
            result = []
            for trace in traces:
                # Convert feedback_scores objects to dicts
                raw_scores = getattr(trace, "feedback_scores", []) or []
                feedback_scores = []
                for score in raw_scores:
                    score_dict = {
                        "name": getattr(score, "name", None),
                        "value": getattr(score, "value", None),
                        "reason": getattr(score, "reason", None),
                    }
                    feedback_scores.append(score_dict)

                trace_dict = {
                    "id": trace.id,
                    "name": trace.name,
                    "input": trace.input,
                    "output": trace.output,
                    "metadata": trace.metadata,
                    "feedback_scores": feedback_scores,
                    "tags": getattr(trace, "tags", []),
                    "created_at": getattr(trace, "created_at", None),
                }
                result.append(trace_dict)
            return result
        except Exception as e:
            logger.error(f"OPIK: Failed to search traces: {e}")
            return []

    def search_spans(
        self,
        filter_string: str | None = None,
        span_type: str | None = None,
        max_results: int = 100,
    ) -> list[dict]:
        """
        Search spans by filter criteria.

        Args:
            filter_string: OQL filter
            span_type: Filter by span type ("general", "llm", "tool") - added to filter_string
            max_results: Maximum number of results

        Returns:
            List of span dicts

        Example:
            spans = tracer.search_spans(
                filter_string="metadata.confidence < 0.5",
                span_type="llm",
                max_results=50,
            )
        """
        if not self.enabled or not self._client:
            return []

        try:
            # Build complete filter string (type must be in filter_string, not separate param)
            full_filter = filter_string
            if span_type:
                type_filter = f'type = "{span_type}"'
                if full_filter:
                    full_filter = f"{full_filter} AND {type_filter}"
                else:
                    full_filter = type_filter

            spans = self._client.search_spans(
                project_name=self._project,
                filter_string=full_filter,
                max_results=max_results,
            )
            # Convert to list of dicts
            result = []
            for span in spans:
                # Convert feedback_scores objects to dicts
                raw_scores = getattr(span, "feedback_scores", []) or []
                feedback_scores = []
                for score in raw_scores:
                    score_dict = {
                        "name": getattr(score, "name", None),
                        "value": getattr(score, "value", None),
                        "reason": getattr(score, "reason", None),
                    }
                    feedback_scores.append(score_dict)

                span_dict = {
                    "id": span.id,
                    "trace_id": span.trace_id,
                    "name": span.name,
                    "type": span.type,
                    "input": span.input,
                    "output": span.output,
                    "metadata": span.metadata,
                    "feedback_scores": feedback_scores,
                    "created_at": getattr(span, "created_at", None),
                }
                result.append(span_dict)
            return result
        except Exception as e:
            logger.error(f"OPIK: Failed to search spans: {e}")
            return []

    def get_client(self):
        """
        Get the underlying Opik client for direct API access.

        Returns:
            Opik client instance or None if not enabled
        """
        return self._client if self.enabled else None

    def create_dataset_from_traces(
        self,
        dataset_name: str,
        trace_ids: list[str],
        description: str | None = None,
    ) -> bool:
        """
        Create a dataset from existing trace IDs.

        This is the Opik-native way to create experiment datasets:
        1. Search for traces matching criteria
        2. Create dataset from those trace IDs

        Args:
            dataset_name: Name for the new dataset
            trace_ids: List of trace IDs to include
            description: Optional dataset description

        Returns:
            True if successful
        """
        if not self.enabled or not self._client:
            return False

        try:
            # Get or create dataset
            dataset = self._client.get_or_create_dataset(
                name=dataset_name,
                description=description or f"Dataset from {len(trace_ids)} traces",
            )

            # Fetch traces and add to dataset
            items = []
            for trace_id in trace_ids:
                try:
                    trace = self._client.get_trace(trace_id)
                    if trace:
                        items.append({
                            "trace_id": trace_id,
                            "input": trace.input or {},
                            "expected_output": trace.output or {},
                            "metadata": {
                                "source_trace_id": trace_id,
                                "trace_name": trace.name,
                            },
                        })
                except Exception as e:
                    logger.warning(f"OPIK: Could not fetch trace {trace_id}: {e}")

            if items:
                dataset.insert(items)
                logger.info(f"OPIK: Created dataset '{dataset_name}' with {len(items)} items")
                return True

            return False

        except Exception as e:
            logger.error(f"OPIK: Failed to create dataset from traces: {e}")
            return False

    def create_dataset_from_spans(
        self,
        dataset_name: str,
        spans: list[dict],
        description: str | None = None,
        mark_added: bool = True,
    ) -> bool:
        """
        Create a dataset from span data (from search_spans).

        This is the Opik-native way to create optimization datasets:
        1. Search for spans matching criteria (e.g., charter_validation with low Correctness)
        2. Pass the span dicts to this method
        3. Creates dataset items from span input/output
        4. Optionally marks spans as added_to_dataset

        Args:
            dataset_name: Name for the new dataset
            spans: List of span dicts (from search_spans), must have id, input, output
            description: Optional dataset description
            mark_added: If True, log feedback to mark spans as added to dataset

        Returns:
            True if successful
        """
        if not self.enabled or not self._client:
            logger.warning("OPIK: create_dataset_from_spans - client not enabled")
            return False

        logger.info(f"OPIK: Creating dataset '{dataset_name}' from {len(spans)} spans")

        try:
            # Get or create dataset
            logger.debug(f"OPIK: get_or_create_dataset('{dataset_name}')")
            dataset = self._client.get_or_create_dataset(
                name=dataset_name,
                description=description or f"Dataset from {len(spans)} spans",
            )
            logger.info(f"OPIK: Dataset '{dataset_name}' created/retrieved successfully")

            # Convert spans to dataset items
            items = []
            for span in spans:
                span_id = span.get("id", "")
                span_input = span.get("input") or {}
                span_output = span.get("output") or {}
                span_metadata = span.get("metadata") or {}

                # Build dataset item with provider/model info from span metadata
                item = {
                    "input": span_input,
                    "expected_output": span_output,
                    "metadata": {
                        "source_span_id": span_id,
                        "source_trace_id": span.get("trace_id", ""),
                        "span_name": span.get("name", ""),
                        "provider": span_metadata.get("provider", ""),
                        "model": span_metadata.get("model", ""),
                    },
                }
                items.append(item)
                logger.debug(f"OPIK: Span {span_id[:12]}... converted, provider={span_metadata.get('provider')}, model={span_metadata.get('model')}")

            logger.info(f"OPIK: Prepared {len(items)} items for dataset")

            if items:
                logger.info(f"OPIK: Inserting {len(items)} items into dataset '{dataset_name}'")
                dataset.insert(items)
                logger.info(f"OPIK: Successfully inserted {len(items)} items into dataset '{dataset_name}'")

                # Mark spans as added to dataset
                if mark_added:
                    span_ids = [s.get("id") for s in spans if s.get("id")]
                    logger.debug(f"OPIK: Marking {len(span_ids)} spans as added_to_dataset")
                    marked = 0
                    for span_id in span_ids:
                        if self.log_span_feedback(
                            span_id=span_id,
                            score=1.0,
                            feedback_type="added_to_dataset",
                            comment=dataset_name,
                        ):
                            marked += 1
                    logger.info(f"OPIK: Marked {marked}/{len(span_ids)} spans as added_to_dataset")

                return True
            else:
                logger.warning(f"OPIK: No items to insert - spans list was empty")
                return False

        except Exception as e:
            import traceback
            logger.error(f"OPIK: Failed to create dataset from spans: {e}")
            logger.error(f"OPIK: Traceback: {traceback.format_exc()}")
            return False

    def update_span_metadata(
        self,
        span_id: str,
        metadata: dict,
    ) -> bool:
        """
        Update metadata for a span.

        Used to mark spans as processed (e.g., added_to_dataset).

        Args:
            span_id: ID of the span to update
            metadata: Metadata dict to merge

        Returns:
            True if successful
        """
        if not self.enabled or not self._client:
            return False

        try:
            # Opik SDK may have update_span or similar method
            # If not available, we use feedback as a workaround
            span = self._client.get_span(span_id)
            if span:
                # Merge with existing metadata
                existing = span.metadata or {}
                existing.update(metadata)
                # Note: Opik SDK may not support direct metadata update
                # In that case, we log feedback as a marker
                if "added_to_dataset" in metadata:
                    self.log_span_feedback(
                        span_id=span_id,
                        score=1.0,
                        feedback_type="added_to_dataset",
                        comment=metadata.get("added_to_dataset", "true"),
                    )
                return True
            return False
        except Exception as e:
            logger.error(f"OPIK: Failed to update span metadata: {e}")
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

    Note:
        Provider information is automatically captured from session settings
        and included in trace metadata.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()

            # Capture provider info at execution time
            provider_info = _get_provider_metadata()

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
                    provider_info=provider_info,
                )

                return result
            except Exception as e:
                tracer.trace_feature(
                    feature_name=feature_name,
                    input_data=input_data,
                    output_data={"error": str(e)},
                    agent_name=agent_name,
                    metadata={"status": "error"},
                    provider_info=provider_info,
                )
                raise

        return wrapper  # type: ignore

    return decorator
