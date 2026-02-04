"""
Opik Experiment Runner Task

Runs scheduled LLM evaluation experiments using Opik-native workflows:
1. Query Opik for traces/spans matching criteria (e.g., low confidence)
2. Create dataset from those trace IDs
3. Run experiment/evaluation on the dataset

This is the correct Opik workflow - we don't create new traces for revalidation,
we query existing traces and add them to datasets for experimentation.

Flow:
1. Search Opik for traces with feedback_scores matching criteria
2. Create dataset with incremental name from those trace IDs
3. Optionally run re-validation to compare results
4. Track improvement metrics
"""

import asyncio
import time
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from app.services.tasks import _task_boilerplate, TaskError, REDIS_SUCCESS_TTL
from app.services.logging import TaskLogger


# Default experiment parameters
DEFAULT_MAX_CONFIDENCE = 0.5
DEFAULT_MAX_ITEMS = 50
DEFAULT_OLLAMA_SLEEP = 2.0


def _get_default_provider() -> str:
    """Get default provider from session settings or fallback."""
    try:
        from app.services.session import get_current_provider

        return get_current_provider()
    except Exception:
        return "ollama"


def _get_default_model() -> str:
    """Get default model from session settings or fallback."""
    try:
        from app.services.session import get_current_model

        return get_current_model()
    except Exception:
        return "mistral"


def _generate_dataset_name(experiment_type: str, date_str: str) -> str:
    """
    Generate incremental dataset name.

    Format: {experiment_type}-{date}-{sequence}
    Example: low-confidence-20260204-001

    Checks existing datasets to find next sequence number.
    """
    from app.agents.tracing import get_tracer

    tracer = get_tracer()
    base_name = f"{experiment_type}-{date_str}"

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
    experiment_type: str = "low_confidence_revalidation",
) -> dict:
    """
    Run scheduled Opik experiments using Opik-native workflows.

    Workflow:
    1. Query Opik for traces with feedback_scores.validation_confidence < threshold
    2. Create dataset from matching trace IDs
    3. Optionally re-validate those contributions to measure improvement
    4. Track metrics in Opik experiment

    Experiment Types:
    - low_confidence_revalidation: Find low-confidence traces, add to dataset
    - category_classification: (future) Evaluate category predictions

    Args:
        date_string: Date in YYYYMMDD format. Defaults to today.
        max_confidence: Maximum confidence threshold for selecting items (default: 0.5)
        max_items: Maximum number of items to process (default: 50)
        provider: LLM provider to use (default: session provider)
        model: Model override (optional)
        ollama_sleep: Sleep time between Ollama validations (default: 2.0s)
        experiment_type: Type of experiment to run

    Returns:
        dict: Result with experiment counts and metrics
    """
    redis_conn, lock_key, success_key, result, task_id, logger = _task_boilerplate(
        "task_opik_experiment", date_string, skip_success_check=True
    )

    # Early exit if skipped (lock held)
    if result["status"] == "skipped":
        return result

    # Apply defaults (use session provider if not specified)
    max_confidence = max_confidence if max_confidence is not None else DEFAULT_MAX_CONFIDENCE
    max_items = max_items if max_items is not None else DEFAULT_MAX_ITEMS
    provider = provider or _get_default_provider()
    model = model or _get_default_model() if provider == "ollama" else model
    ollama_sleep = ollama_sleep if ollama_sleep is not None else DEFAULT_OLLAMA_SLEEP

    try:
        # Initialize counters
        result["experiment_type"] = experiment_type
        result["max_confidence"] = max_confidence
        result["max_items"] = max_items
        result["provider"] = provider
        result["model"] = model
        result["dataset_name"] = None
        result["traces_found"] = 0
        result["traces_added_to_dataset"] = 0
        result["revalidations_run"] = 0
        result["items_improved"] = 0
        result["items_unchanged"] = 0
        result["items_degraded"] = 0
        result["metrics"] = {}

        # Check if Opik is configured
        from app.agents.tracing import get_tracer

        tracer = get_tracer()
        if not tracer.enabled:
            result["status"] = "skipped"
            result["reason"] = "opik_not_configured"
            result["warnings"].append("Opik tracing not enabled - cannot run Opik-native experiment")
            logger.log_progress("Opik not configured - skipping experiment")
            return result

        # Run the appropriate experiment
        if experiment_type == "low_confidence_revalidation":
            _run_low_confidence_experiment(
                result=result,
                max_confidence=max_confidence,
                max_items=max_items,
                provider=provider,
                model=model,
                ollama_sleep=ollama_sleep,
                tracer=tracer,
                logger=logger,
                date_string=date_string or datetime.now().strftime("%Y%m%d"),
            )
        else:
            result["warnings"].append(f"Unknown experiment type: {experiment_type}")
            result["status"] = "skipped"
            result["reason"] = "unknown_experiment_type"
            return result

        # Mark task as completed
        result["status"] = "success"
        redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)

        logger.log_completed(
            status="success",
            dataset=result.get("dataset_name"),
            traces_found=result["traces_found"],
            traces_added=result["traces_added_to_dataset"],
            revalidations=result["revalidations_run"],
            improved=result["items_improved"],
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


def _run_low_confidence_experiment(
    result: dict,
    max_confidence: float,
    max_items: int,
    provider: str,
    model: Optional[str],
    ollama_sleep: float,
    tracer,
    logger: TaskLogger,
    date_string: str,
) -> None:
    """
    Run low-confidence experiment using Opik-native workflow.

    Flow:
    1. Query Opik for traces with validation_confidence < threshold
    2. Create dataset from those trace IDs
    3. Optionally re-validate to measure improvement

    Args:
        result: Result dict to populate
        max_confidence: Maximum confidence threshold
        max_items: Maximum items to process
        provider: LLM provider
        model: Optional model override
        ollama_sleep: Sleep between Ollama calls
        tracer: Opik tracer instance
        logger: TaskLogger instance
        date_string: Date string for naming
    """
    # Step 1: Query Opik for low-confidence traces
    logger.log_progress(f"Querying Opik for traces with validation_confidence < {max_confidence}")

    filter_string = f"feedback_scores.validation_confidence < {max_confidence}"

    traces = tracer.search_traces(
        filter_string=filter_string,
        max_results=max_items,
    )

    result["traces_found"] = len(traces)
    logger.log_progress(f"Found {len(traces)} traces matching criteria")

    if not traces:
        result["warnings"].append(f"No traces found with validation_confidence < {max_confidence}")
        logger.log_progress("No matching traces found - experiment complete")
        return

    # Step 2: Create dataset from trace IDs
    dataset_name = _generate_dataset_name("low-confidence", date_string)
    result["dataset_name"] = dataset_name

    logger.log_progress(f"Creating Opik dataset: {dataset_name}")

    trace_ids = [t["id"] for t in traces]

    success = tracer.create_dataset_from_traces(
        dataset_name=dataset_name,
        trace_ids=trace_ids,
        description=f"Low-confidence traces (< {max_confidence}) for revalidation experiment",
    )

    if success:
        result["traces_added_to_dataset"] = len(trace_ids)
        logger.log_progress(f"Added {len(trace_ids)} traces to dataset '{dataset_name}'")
    else:
        result["warnings"].append("Failed to create dataset from traces")
        logger.log_progress("Warning: Could not create dataset from traces")

    # Step 3: Optionally run re-validation on these items
    # This re-validates the contributions and logs NEW traces with (hopefully) better confidence
    # The new traces will have feedback scores that can be compared to the originals

    run_revalidation = True  # Could make this configurable

    if run_revalidation and traces:
        logger.log_progress("Running re-validation on low-confidence items")

        from app.agents.forseti import ForsetiAgent
        from app.providers import get_provider

        llm_provider = get_provider(provider, model=model, cache=False)
        agent = ForsetiAgent(provider=llm_provider)

        confidence_before = []
        confidence_after = []

        for i, trace_data in enumerate(traces):
            logger.log_progress(
                f"Re-validating {i+1}/{len(traces)}",
                current=i + 1,
                total=len(traces),
            )

            try:
                # Extract input from trace
                input_data = trace_data.get("input", {})
                title = input_data.get("title", "")
                body = input_data.get("body", "")
                category = input_data.get("category")

                if not title and not body:
                    continue

                # Get original confidence from feedback scores
                original_confidence = 0.0
                for score in trace_data.get("feedback_scores", []):
                    if score.get("name") == "validation_confidence":
                        original_confidence = score.get("value", 0.0)
                        break

                confidence_before.append(original_confidence)

                # Re-run validation (this creates a NEW trace with new feedback scores)
                new_result = asyncio.run(
                    agent.validate(
                        title=title,
                        body=body,
                        category=category,
                    )
                )

                new_confidence = new_result.confidence
                confidence_after.append(new_confidence)

                # Track improvement
                if new_confidence > original_confidence:
                    result["items_improved"] += 1
                elif new_confidence < original_confidence:
                    result["items_degraded"] += 1
                else:
                    result["items_unchanged"] += 1

                result["revalidations_run"] += 1

                # Sleep between Ollama calls
                if provider.startswith("ollama") and ollama_sleep > 0:
                    time.sleep(ollama_sleep)

            except Exception as e:
                logger.log_progress(f"Error re-validating trace {trace_data.get('id', '?')[:8]}: {str(e)[:50]}")
                result["warnings"].append(f"Revalidation error: {str(e)[:50]}")

        # Calculate metrics
        if confidence_before and confidence_after:
            avg_before = sum(confidence_before) / len(confidence_before)
            avg_after = sum(confidence_after) / len(confidence_after)

            result["metrics"] = {
                "avg_confidence_before": round(avg_before, 3),
                "avg_confidence_after": round(avg_after, 3),
                "confidence_delta": round(avg_after - avg_before, 3),
                "improvement_rate": round(result["items_improved"] / len(confidence_after), 3) if confidence_after else 0,
                "degradation_rate": round(result["items_degraded"] / len(confidence_after), 3) if confidence_after else 0,
            }

            logger.log_progress(
                f"Revalidation complete: improved={result['items_improved']}, "
                f"degraded={result['items_degraded']}, delta={result['metrics']['confidence_delta']}"
            )

    logger.log_progress(f"Experiment complete. Dataset '{dataset_name}' available in Opik")


# Alias for backward compatibility
run_opik_experiment = task_opik_experiment
