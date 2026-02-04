"""
Opik Experiment Dataset Builder Task

Creates optimization datasets from charter_validation spans using Opik-native workflow:
1. Search Opik for charter_validation spans
2. Filter by Correctness feedback score (low scores = optimization candidates)
3. Exclude spans already added_to_dataset
4. Create dataset for prompt optimization (separate optimization task)

This is the correct Opik workflow - we query existing spans and create datasets.
The actual optimization runs as a separate task against the dataset.

Flow:
1. Search Opik for charter_validation spans with Correctness < threshold
2. Filter out spans already marked as added_to_dataset
3. Create dataset with incremental name from those span IDs
4. Mark spans as added_to_dataset to avoid duplicates
"""

from datetime import datetime
from typing import Optional

from app.services.tasks import (
    _task_boilerplate,
    TaskError,
    REDIS_SUCCESS_TTL,
    AGENT_FEATURE_REGISTRY,
    get_feature_config,
    get_feature_prompt,
)
from app.services.logging import TaskLogger


# Default parameters
DEFAULT_MAX_CORRECTNESS = 0.7  # Spans with Correctness below this are candidates
DEFAULT_MAX_ITEMS = 100


def _generate_dataset_name(prefix: str, date_str: str) -> str:
    """
    Generate incremental dataset name.

    Format: {prefix}-{date}-{sequence}
    Example: charter-optimization-20260204-001

    Checks existing datasets to find next sequence number.
    """
    from app.agents.tracing import get_tracer

    tracer = get_tracer()
    base_name = f"{prefix}-{date_str}"

    # If Opik not available, just use timestamp
    if not tracer.enabled or not tracer._client:
        timestamp = datetime.now().strftime("%H%M%S")
        return f"{base_name}-{timestamp}"

    # Try to find existing datasets and increment
    try:
        for seq in range(1, 100):
            name = f"{base_name}-{seq:03d}"
            try:
                tracer._client.get_dataset(name=name)
                # Dataset exists, continue to next sequence
            except Exception:
                # Dataset doesn't exist, use this name
                return name

        # Fallback with timestamp if too many sequences
        timestamp = datetime.now().strftime("%H%M%S")
        return f"{base_name}-{timestamp}"

    except Exception:
        timestamp = datetime.now().strftime("%H%M%S")
        return f"{base_name}-{timestamp}"


def task_opik_experiment(
    date_string: str = None,
    max_confidence: float = None,
    max_items: int = None,
    provider: str = None,
    model: str = None,
    ollama_sleep: float = None,
    experiment_type: str = "charter_optimization",
) -> dict:
    """
    Build optimization dataset from charter_validation spans using Opik-native workflow.

    Workflow:
    1. Query Opik for charter_validation spans with Correctness < threshold
    2. Exclude spans already added_to_dataset
    3. Create optimization dataset from matching span IDs
    4. Mark spans as added_to_dataset

    Note: This task only BUILDS the dataset. The actual optimization
    runs as a separate task (task_prompt_optimization).

    Args:
        date_string: Date in YYYYMMDD format. Defaults to today.
        max_confidence: Maximum Correctness threshold (default: 0.7)
        max_items: Maximum number of items to include (default: 100)
        provider: Not used (kept for API compatibility)
        model: Not used (kept for API compatibility)
        ollama_sleep: Not used (kept for API compatibility)
        experiment_type: Type of dataset to build (default: charter_optimization)

    Returns:
        dict: Result with dataset info and counts
    """
    redis_conn, lock_key, success_key, result, task_id, logger = _task_boilerplate(
        "task_opik_experiment", date_string, skip_success_check=True
    )

    # Early exit if skipped (lock held)
    if result["status"] == "skipped":
        return result

    # Apply defaults
    max_correctness = max_confidence if max_confidence is not None else DEFAULT_MAX_CORRECTNESS
    max_items = max_items if max_items is not None else DEFAULT_MAX_ITEMS

    try:
        # Initialize result counters
        result["experiment_type"] = experiment_type
        result["max_correctness"] = max_correctness
        result["max_items"] = max_items
        result["dataset_name"] = None
        result["spans_found"] = 0
        result["spans_already_in_dataset"] = 0
        result["spans_added_to_dataset"] = 0

        # Check if Opik is configured
        from app.agents.tracing import get_tracer

        tracer = get_tracer()
        if not tracer.enabled:
            result["status"] = "skipped"
            result["reason"] = "opik_not_configured"
            result["warnings"].append("Opik tracing not enabled - cannot build Opik dataset")
            logger.log_progress("Opik not configured - skipping")
            return result

        # Get feature configuration from registry
        feature_config = get_feature_config(experiment_type)
        if not feature_config:
            available = ", ".join(AGENT_FEATURE_REGISTRY.keys())
            result["warnings"].append(
                f"Unknown experiment type: {experiment_type}. Available: {available}"
            )
            result["status"] = "skipped"
            result["reason"] = "unknown_experiment_type"
            return result

        # Run the dataset builder using registry configuration
        _build_span_optimization_dataset(
            result=result,
            span_name=feature_config["feature"],
            dataset_prefix=feature_config["dataset_prefix"],
            max_correctness=max_correctness,
            max_items=max_items,
            tracer=tracer,
            logger=logger,
            date_string=date_string or datetime.now().strftime("%Y%m%d"),
        )
        result["agent"] = feature_config["agent"]
        result["feature_description"] = feature_config["description"]
        result["prompt_key"] = feature_config.get("prompt_key")

        # Get prompt metadata for optimization reference
        _, prompt_metadata = get_feature_prompt(experiment_type)
        if prompt_metadata:
            result["prompt_info"] = prompt_metadata

        # Mark task as completed
        result["status"] = "success"
        redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)

        logger.log_completed(
            status="success",
            dataset=result.get("dataset_name"),
            spans_found=result["spans_found"],
            spans_added=result["spans_added_to_dataset"],
        )
        return result

    except Exception as e:
        result["status"] = "failed"
        result["errors"].append(str(e))
        logger.log_failed(error=str(e), recoverable=False)
        raise TaskError("failed", str(e))

    finally:
        # Always release lock
        redis_conn.delete(lock_key)


def _build_span_optimization_dataset(
    result: dict,
    span_name: str,
    dataset_prefix: str,
    max_correctness: float,
    max_items: int,
    tracer,
    logger: TaskLogger,
    date_string: str,
) -> None:
    """
    Build optimization dataset from spans with low Correctness scores.

    Flow:
    1. Search for spans by name with Correctness < threshold
    2. Filter out spans already added_to_dataset
    3. Create dataset from remaining spans
    4. Mark spans as added_to_dataset

    Args:
        result: Result dict to populate
        span_name: Name of the span to search for (e.g., "charter_validation", "category_classification")
        dataset_prefix: Prefix for the dataset name (e.g., "charter-optimization")
        max_correctness: Maximum Correctness threshold
        max_items: Maximum items to include
        tracer: Opik tracer instance
        logger: TaskLogger instance
        date_string: Date string for naming
    """
    # Step 1: Query Opik for spans with low Correctness
    logger.log_progress(f"Searching for {span_name} spans with Correctness < {max_correctness}")

    # Build filter for spans with low Correctness
    # OQL filter: name = "span_name" AND feedback_scores.Correctness < threshold
    filter_string = f'name = "{span_name}" AND feedback_scores.Correctness < {max_correctness}'
    logger.log_progress(f"OQL filter: {filter_string}")

    spans = tracer.search_spans(
        filter_string=filter_string,
        span_type="llm",
        max_results=max_items * 2,  # Fetch extra to account for filtering
    )

    result["spans_found"] = len(spans)
    result["span_name"] = span_name
    result["filter_string"] = filter_string
    logger.log_progress(f"Found {len(spans)} {span_name} spans matching criteria")

    # Log span IDs for debugging
    if spans:
        span_ids_preview = [s.get("id", "?")[:12] + "..." for s in spans[:5]]
        logger.log_progress(f"First span IDs: {span_ids_preview}")

    if not spans:
        result["warnings"].append(f"No {span_name} spans found with Correctness < {max_correctness}")
        logger.log_progress("No matching spans found - dataset not created")
        return

    # Step 2: Filter out spans already added to a dataset
    # Check for added_to_dataset feedback score
    new_spans = []
    for span in spans:
        # Check if already added to dataset
        feedback_scores = span.get("feedback_scores", [])
        already_added = False
        for score in feedback_scores:
            if score.get("name") == "added_to_dataset":
                already_added = True
                result["spans_already_in_dataset"] += 1
                break

        if not already_added:
            new_spans.append(span)

        # Stop if we have enough new spans
        if len(new_spans) >= max_items:
            break

    logger.log_progress(
        f"After filtering: {len(new_spans)} new spans "
        f"({result['spans_already_in_dataset']} already in datasets)"
    )

    if not new_spans:
        result["warnings"].append("All matching spans already added to datasets")
        logger.log_progress("No new spans to add - dataset not created")
        return

    # Step 3: Create dataset from spans (pass full span data, not just IDs)
    dataset_name = _generate_dataset_name(dataset_prefix, date_string)
    result["dataset_name"] = dataset_name

    logger.log_progress(f"Creating Opik dataset: {dataset_name}")

    span_ids = [s["id"] for s in new_spans]
    result["span_ids"] = span_ids  # Store for debugging

    logger.log_progress(f"Spans to add ({len(new_spans)}): {[sid[:12] + '...' for sid in span_ids[:5]]}")

    success = tracer.create_dataset_from_spans(
        dataset_name=dataset_name,
        spans=new_spans,  # Pass full span dicts, not just IDs
        description=f"{span_name} spans (Correctness < {max_correctness}) for prompt optimization",
        mark_added=True,  # Mark spans as added_to_dataset
    )

    logger.log_progress(f"create_dataset_from_spans returned: {success}")

    if success:
        result["spans_added_to_dataset"] = len(new_spans)
        logger.log_progress(f"SUCCESS: Added {len(new_spans)} spans to dataset '{dataset_name}'")
    else:
        result["warnings"].append("Failed to create dataset from spans - check opik logs")
        logger.log_progress("FAILED: Could not create dataset from spans - see opik domain logs")

    # Log sample data for debugging
    if new_spans:
        sample = new_spans[0]
        correctness = None
        for score in sample.get("feedback_scores", []):
            if score.get("name") == "Correctness":
                correctness = score.get("value")
                break
        logger.log_progress(
            f"Sample span: {sample.get('id', '?')[:8]}... Correctness={correctness}"
        )

    logger.log_progress(f"Dataset '{dataset_name}' ready for optimization")


# Alias for backward compatibility
run_opik_experiment = task_opik_experiment
