"""
Opik Evaluate Task

Scheduled task that:
1. Cleans up error traces (optional, default: True)
2. Searches for recent spans (charter_validation, category_classification)
3. Creates a dataset from spans not yet added to a dataset
4. Runs Opik evaluate() with configured metrics including output_format
5. Reports results

This task should run periodically (e.g., every 30 minutes) to process
spans that have been created since the last run.

The spans take ~3 minutes to appear in Opik after creation, so this
task handles the async nature of span ingestion.

Pre-experiment cleanup removes traces with validation errors to avoid
polluting the optimization process.

IMPORTANT: This task defaults to gemini for evaluation to avoid
conflicts with Ollama (which may be used by other tasks).
If task_provider="ollama" is specified, it will check the global
Ollama lock before proceeding.
"""

from datetime import datetime, timedelta
from typing import Optional

from app.services.tasks import (
    _task_boilerplate,
    TaskError,
    REDIS_SUCCESS_TTL,
    AGENT_FEATURE_REGISTRY,
    get_feature_config,
)
from app.services.logging import TaskLogger


# Default parameters
DEFAULT_MAX_ITEMS = 50
DEFAULT_LOOKBACK_HOURS = 24  # Look for spans from last 24 hours


def task_opik_evaluate(
    date_string: str = None,
    experiment_type: str = "charter_optimization",
    max_items: int = None,
    lookback_hours: int = None,
    metrics: list[str] = None,
    task_provider: str = None,
    skip_if_empty: bool = True,
    cleanup_errors: bool = True,
) -> dict:
    """
    Create dataset from recent spans and run Opik evaluate().

    This task is designed to run periodically (via scheduler) to:
    1. (Optional) Clean up error traces to avoid polluting optimization
    2. Find spans created in the last N hours that haven't been added to a dataset
    3. Create a dataset from those spans
    4. Run Opik evaluate() with the configured metrics
    5. Mark spans as processed

    Args:
        date_string: Date in YYYYMMDD format. Defaults to today.
        experiment_type: Type from AGENT_FEATURE_REGISTRY (default: charter_optimization)
        max_items: Maximum spans to include (default: 50)
        lookback_hours: Hours to look back for spans (default: 24)
        metrics: List of Opik metrics to use (default: ["hallucination", "output_format"])
        task_provider: LLM provider for evaluation task (default: from session or gemini)
        skip_if_empty: If True, skip without error if no new spans found
        cleanup_errors: If True, delete error traces before creating dataset

    Returns:
        dict: Result with dataset info, experiment results, and counts
    """
    # Use skip_success_check=True so task can run multiple times per day
    redis_conn, lock_key, success_key, result, task_id, logger = _task_boilerplate(
        "task_opik_evaluate", date_string, skip_success_check=True
    )

    # Early exit if skipped (lock held)
    if result["status"] == "skipped":
        return result

    # Apply defaults
    max_items = max_items if max_items is not None else DEFAULT_MAX_ITEMS
    lookback_hours = lookback_hours if lookback_hours is not None else DEFAULT_LOOKBACK_HOURS
    metrics = metrics or ["hallucination", "output_format"]  # Include output_format by default
    task_provider = task_provider or "gemini"

    # Check Ollama lock if using Ollama (avoid conflicts with other tasks)
    if task_provider == "ollama":
        from app.services.scheduler.utils import get_scheduler_redis, sched_key
        l = get_scheduler_redis()
        if l.exists(sched_key("lock:ollama:global")):
            result["warnings"].append("Ollama is locked by another task, using gemini instead")
            task_provider = "gemini"  # Failover to gemini
            logger.log_progress("Ollama locked, failing over to gemini")

    try:
        # Initialize result
        result["experiment_type"] = experiment_type
        result["max_items"] = max_items
        result["lookback_hours"] = lookback_hours
        result["metrics"] = metrics
        result["task_provider"] = task_provider
        result["cleanup_errors"] = cleanup_errors
        result["cleanup_result"] = None
        result["dataset_name"] = None
        result["spans_found"] = 0
        result["spans_new"] = 0
        result["experiment_result"] = None

        # Step 0: Cleanup error traces before processing
        if cleanup_errors:
            logger.log_progress("Cleaning up error traces...")
            from app.processors.workflows.workflow_experiment import cleanup_error_traces
            cleanup_result = cleanup_error_traces()
            result["cleanup_result"] = cleanup_result
            if cleanup_result.get("deleted", 0) > 0:
                logger.log_progress(f"Deleted {cleanup_result['deleted']} error traces")

        # Check Opik configuration
        from app.agents.tracing import get_tracer

        tracer = get_tracer()
        if not tracer.enabled:
            result["status"] = "skipped"
            result["reason"] = "opik_not_configured"
            result["warnings"].append("Opik tracing not enabled")
            logger.log_progress("Opik not configured - skipping")
            return result

        # Get feature configuration
        feature_config = get_feature_config(experiment_type)
        if not feature_config:
            available = ", ".join(AGENT_FEATURE_REGISTRY.keys())
            result["status"] = "skipped"
            result["reason"] = "unknown_experiment_type"
            result["warnings"].append(f"Unknown experiment type: {experiment_type}. Available: {available}")
            return result

        span_name = feature_config["feature"]
        dataset_prefix = feature_config["dataset_prefix"]
        logger.log_progress(f"Looking for {span_name} spans from last {lookback_hours}h")

        # Step 1: Search for recent spans not yet added to dataset
        spans = _find_recent_spans(
            tracer=tracer,
            span_name=span_name,
            max_items=max_items,
            logger=logger,
        )

        result["spans_found"] = len(spans)

        # Filter out spans already added to dataset
        new_spans = []
        for span in spans:
            feedback_scores = span.get("feedback_scores", [])
            already_added = any(
                s.get("name") == "added_to_dataset" for s in feedback_scores
            )
            if not already_added:
                new_spans.append(span)

        result["spans_new"] = len(new_spans)
        logger.log_progress(f"Found {len(spans)} spans, {len(new_spans)} not yet in dataset")

        if not new_spans:
            if skip_if_empty:
                result["status"] = "skipped"
                result["reason"] = "no_new_spans"
                result["warnings"].append("No new spans found to process")
                logger.log_progress("No new spans - skipping")
                return result
            else:
                result["warnings"].append("No new spans found")

        # Step 2: Create dataset from spans
        if new_spans:
            today = datetime.now().strftime("%Y%m%d")
            timestamp = datetime.now().strftime("%H%M%S")
            dataset_name = f"{dataset_prefix}-{today}-{timestamp}"
            result["dataset_name"] = dataset_name

            logger.log_progress(f"Creating dataset: {dataset_name}")

            success = tracer.create_dataset_from_spans(
                dataset_name=dataset_name,
                spans=new_spans,
                description=f"{span_name} spans for evaluation ({len(new_spans)} items)",
                mark_added=True,
            )

            if not success:
                result["status"] = "failed"
                result["errors"].append("Failed to create dataset from spans")
                logger.log_failed(error="Dataset creation failed")
                return result

            logger.log_progress(f"Dataset created: {dataset_name} ({len(new_spans)} items)")

            # Step 3: Run Opik evaluate()
            logger.log_progress(f"Running experiment with metrics: {metrics}")

            experiment_result = _run_experiment(
                dataset_name=dataset_name,
                experiment_type=experiment_type,
                metrics=metrics,
                task_provider=task_provider,
                logger=logger,
            )

            result["experiment_result"] = experiment_result

            if experiment_result.get("status") == "success":
                logger.log_progress("Experiment completed successfully")
            else:
                result["warnings"].append(f"Experiment issues: {experiment_result.get('errors', [])}")

        # Mark success
        result["status"] = "success"
        redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)

        logger.log_completed(
            status="success",
            dataset=result.get("dataset_name"),
            spans_found=result["spans_found"],
            spans_new=result["spans_new"],
        )
        return result

    except Exception as e:
        result["status"] = "failed"
        result["errors"].append(str(e))
        logger.log_failed(error=str(e), recoverable=False)
        raise TaskError("failed", str(e))

    finally:
        redis_conn.delete(lock_key)


def _find_recent_spans(
    tracer,
    span_name: str,
    max_items: int,
    logger: TaskLogger,
) -> list[dict]:
    """
    Find recent spans by name.

    Args:
        tracer: Opik tracer instance
        span_name: Name of span to search for
        max_items: Maximum results
        logger: TaskLogger instance

    Returns:
        List of span dicts
    """
    # Build filter - just search by name, Opik will return most recent
    filter_string = f'name = "{span_name}"'
    logger.log_progress(f"Searching spans: {filter_string}")

    spans = tracer.search_spans(
        filter_string=filter_string,
        span_type="llm",
        max_results=max_items * 2,  # Get extra to account for filtering
    )

    return spans[:max_items]


def _run_experiment(
    dataset_name: str,
    experiment_type: str,
    metrics: list[str],
    task_provider: str,
    logger: TaskLogger,
) -> dict:
    """
    Run Opik evaluate() on a dataset.

    Args:
        dataset_name: Name of dataset to evaluate
        experiment_type: Type from AGENT_FEATURE_REGISTRY
        metrics: List of metric names
        task_provider: LLM provider for task
        logger: TaskLogger instance

    Returns:
        dict with experiment results
    """
    from app.processors.workflows import OpikExperimentConfig, run_opik_experiment

    today = datetime.now().strftime("%Y%m%d")
    timestamp = datetime.now().strftime("%H%M%S")
    experiment_name = f"{experiment_type}-eval-{today}-{timestamp}"

    logger.log_progress(f"Starting experiment: {experiment_name}")

    try:
        config = OpikExperimentConfig(
            experiment_name=experiment_name,
            dataset_name=dataset_name,
            experiment_type=experiment_type,
            metrics=metrics,
            task_provider=task_provider,
            cleanup_errors=False,  # Already cleaned at task start
        )

        result = run_opik_experiment(config)
        return result

    except Exception as e:
        logger.log_progress(f"Experiment error: {e}")
        return {
            "status": "failed",
            "errors": [str(e)],
            "experiment_name": experiment_name,
        }
