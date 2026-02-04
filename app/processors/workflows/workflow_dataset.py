"""
Dataset Creation Workflow

Creates Opik datasets from various sources for prompt optimization experiments.

Sources:
- Opik spans (filtered by Correctness feedback)
- MockupStorage records (filtered by confidence)
- GitHub issues

Dataset item format:
{
    "id": "unique-id",
    "input": {
        "title": "...",
        "body": "...",
        "category": "...",
        "original_confidence": 0.8,
        "original_is_valid": true,
        "record_id": "source_id"
    },
    "expected_output": {
        "is_valid": true,
        "confidence_threshold": 1.0
    },
    "tags": [],
    "created_at": "ISO timestamp"
}
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.services.logging import get_logger
from app.services.tasks import AGENT_FEATURE_REGISTRY, get_feature_config

logger = get_logger("processors")


def create_dataset_from_spans(
    experiment_type: str,
    dataset_name: str,
    max_correctness: float = 0.7,
    max_items: int = 100,
    description: Optional[str] = None,
    save_local: bool = True,
    task_provider: Optional[str] = None,
) -> dict:
    """
    Create an Opik dataset from spans filtered by Correctness score.

    Args:
        experiment_type: Key from AGENT_FEATURE_REGISTRY (e.g., "charter_optimization")
        dataset_name: Name for the dataset
        max_correctness: Include spans with Correctness < this value
        max_items: Maximum items to include
        description: Optional dataset description
        save_local: If True, save dataset items to local JSON file
        task_provider: LLM provider used for validation (for metadata tracking)

    Returns:
        dict with dataset info and item count
    """
    logger.info(f"Creating dataset '{dataset_name}' from spans")
    logger.info(f"  experiment_type: {experiment_type}")
    logger.info(f"  max_correctness: {max_correctness}")
    logger.info(f"  max_items: {max_items}")
    logger.info(f"  task_provider: {task_provider}")

    result = {
        "dataset_name": dataset_name,
        "experiment_type": experiment_type,
        "source": "opik_spans",
        "task_provider": task_provider,
        "max_correctness": max_correctness,
        "items_created": 0,
        "items_skipped": 0,
        "errors": [],
    }

    # Get feature config
    feature_config = get_feature_config(experiment_type)
    if not feature_config:
        result["errors"].append(f"Unknown experiment type: {experiment_type}")
        logger.error(f"Unknown experiment type: {experiment_type}")
        return result

    span_name = feature_config["feature"]
    logger.info(f"  span_name: {span_name}")

    # Get tracer
    from app.agents.tracing import get_tracer
    tracer = get_tracer()

    if not tracer.enabled:
        result["errors"].append("Opik not configured")
        logger.error("Opik not configured")
        return result

    # Build filter
    filter_string = f'name = "{span_name}" AND feedback_scores.Correctness < {max_correctness}'
    logger.info(f"  filter: {filter_string}")

    # Search spans
    spans = tracer.search_spans(
        filter_string=filter_string,
        span_type="llm",
        max_results=max_items * 2,
    )
    logger.info(f"  found {len(spans)} spans matching filter")

    if not spans:
        result["errors"].append("No spans found matching criteria")
        return result

    # Filter out already-added spans and convert to dataset items
    items = []
    for span in spans:
        # Check if already added to a dataset
        feedback_scores = span.get("feedback_scores", [])
        already_added = any(
            s.get("name") == "added_to_dataset" for s in feedback_scores
        )
        if already_added:
            result["items_skipped"] += 1
            continue

        # Extract Correctness value
        correctness = None
        for score in feedback_scores:
            if score.get("name") == "Correctness":
                correctness = score.get("value")
                break

        # Extract input/output from span
        span_input = span.get("input", {})
        span_output = span.get("output", {})

        # Build dataset item
        item = _span_to_dataset_item(
            span_id=span.get("id"),
            span_input=span_input,
            span_output=span_output,
            correctness=correctness,
        )

        if item:
            items.append(item)
            if len(items) >= max_items:
                break

    logger.info(f"  converted {len(items)} spans to dataset items")
    logger.info(f"  skipped {result['items_skipped']} already-added spans")

    if not items:
        result["errors"].append("No new items to add")
        return result

    # Create Opik dataset
    try:
        client = tracer.get_client()
        if client:
            # Build description with metadata
            if not description:
                provider_info = f", task_provider={task_provider}" if task_provider else ""
                description = f"Dataset from {span_name} spans (Correctness < {max_correctness}{provider_info})"

            dataset = client.get_or_create_dataset(
                name=dataset_name,
                description=description,
            )

            # Insert items
            dataset.insert(items)
            result["items_created"] = len(items)
            logger.info(f"  created Opik dataset '{dataset_name}' with {len(items)} items")

            # Mark spans as added
            for item in items:
                source_span_id = item.get("input", {}).get("record_id")
                if source_span_id and source_span_id.startswith("span_"):
                    actual_span_id = source_span_id[5:]  # Remove "span_" prefix
                    tracer.log_span_feedback(
                        span_id=actual_span_id,
                        score=1.0,
                        feedback_type="added_to_dataset",
                        comment=dataset_name,
                    )

    except Exception as e:
        result["errors"].append(f"Failed to create Opik dataset: {e}")
        logger.error(f"Failed to create Opik dataset: {e}")

    # Save local copy
    if save_local and items:
        local_path = _save_dataset_local(dataset_name, items)
        result["local_path"] = str(local_path)
        logger.info(f"  saved local copy to {local_path}")

    return result


def create_dataset_from_storage(
    dataset_name: str,
    max_confidence: float = 0.7,
    max_items: int = 100,
    description: Optional[str] = None,
    save_local: bool = True,
) -> dict:
    """
    Create an Opik dataset from MockupStorage records.

    Args:
        dataset_name: Name for the dataset
        max_confidence: Include records with confidence < this value
        max_items: Maximum items to include
        description: Optional dataset description
        save_local: If True, save dataset items to local JSON file

    Returns:
        dict with dataset info and item count
    """
    logger.info(f"Creating dataset '{dataset_name}' from MockupStorage")
    logger.info(f"  max_confidence: {max_confidence}")
    logger.info(f"  max_items: {max_items}")

    result = {
        "dataset_name": dataset_name,
        "source": "mockup_storage",
        "items_created": 0,
        "items_skipped": 0,
        "errors": [],
    }

    try:
        from app.mockup.storage import get_storage
        storage = get_storage()
        all_records = storage.get_latest_validations(limit=1000)

        # Filter by confidence
        candidates = [
            r for r in all_records
            if r.confidence < max_confidence and r.confidence > 0
        ]
        logger.info(f"  found {len(candidates)} records with confidence < {max_confidence}")

        if not candidates:
            result["errors"].append("No records found matching criteria")
            return result

        # Convert to dataset items
        items = []
        for record in candidates[:max_items]:
            item = _record_to_dataset_item(record)
            if item:
                items.append(item)

        logger.info(f"  converted {len(items)} records to dataset items")

        # Create Opik dataset
        from app.agents.tracing import get_tracer
        tracer = get_tracer()

        if tracer.enabled:
            client = tracer.get_client()
            if client:
                dataset = client.get_or_create_dataset(
                    name=dataset_name,
                    description=description or f"Dataset from MockupStorage (confidence < {max_confidence})",
                )
                dataset.insert(items)
                result["items_created"] = len(items)
                logger.info(f"  created Opik dataset '{dataset_name}' with {len(items)} items")

        # Save local copy
        if save_local and items:
            local_path = _save_dataset_local(dataset_name, items)
            result["local_path"] = str(local_path)
            logger.info(f"  saved local copy to {local_path}")

    except Exception as e:
        result["errors"].append(f"Failed to create dataset: {e}")
        logger.error(f"Failed to create dataset: {e}")

    return result


def _span_to_dataset_item(
    span_id: str,
    span_input: dict,
    span_output: dict,
    correctness: Optional[float],
) -> Optional[dict]:
    """Convert a span to dataset item format."""
    # Extract title/body from span input
    title = span_input.get("title", "")
    body = span_input.get("body", "")

    if not title and not body:
        return None

    # Extract validation result from span output
    is_valid = span_output.get("is_valid", True)
    confidence = span_output.get("confidence", correctness or 0.5)
    category = span_output.get("category", span_input.get("category", ""))

    return {
        "id": str(uuid.uuid4()),
        "input": {
            "title": title[:100] + "..." if len(title) > 100 else title,
            "body": body,
            "category": category,
            "original_confidence": confidence,
            "original_is_valid": is_valid,
            "record_id": f"span_{span_id}",
        },
        "expected_output": {
            "is_valid": is_valid,
            "confidence_threshold": 1.0,  # Target: high confidence
        },
        "tags": [],
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


def _record_to_dataset_item(record) -> Optional[dict]:
    """Convert a MockupStorage record to dataset item format."""
    if not record.title and not record.body:
        return None

    return {
        "id": str(uuid.uuid4()),
        "input": {
            "title": record.title[:100] + "..." if len(record.title) > 100 else record.title,
            "body": record.body,
            "category": record.category or "",
            "original_confidence": record.confidence,
            "original_is_valid": record.is_valid,
            "record_id": f"record_{record.id}",
        },
        "expected_output": {
            "is_valid": record.is_valid,
            "confidence_threshold": 1.0,
        },
        "tags": [],
        "created_at": datetime.utcnow().isoformat() + "Z",
    }


def _save_dataset_local(dataset_name: str, items: list) -> Path:
    """Save dataset items to local JSON file."""
    workflows_dir = Path(__file__).parent
    filename = f"{dataset_name}-dataset-items.json"
    filepath = workflows_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    return filepath


def list_datasets() -> list[dict]:
    """List all available Opik datasets."""
    from app.agents.tracing import get_tracer

    tracer = get_tracer()
    if not tracer.enabled:
        logger.debug("list_datasets: Opik not enabled")
        return []

    try:
        client = tracer.get_client()
        if not client:
            logger.debug("list_datasets: No Opik client")
            return []

        # Try different SDK methods for listing datasets
        datasets = None

        # Method 1: get_datasets() (Opik SDK >= 1.0)
        if hasattr(client, "get_datasets"):
            try:
                datasets = client.get_datasets()
                logger.debug(f"list_datasets: get_datasets() returned {len(list(datasets)) if datasets else 0}")
            except Exception as e:
                logger.debug(f"list_datasets: get_datasets() failed: {e}")

        # Method 2: search_datasets() or list_datasets()
        if datasets is None and hasattr(client, "search_datasets"):
            try:
                datasets = client.search_datasets()
                logger.debug(f"list_datasets: search_datasets() returned {len(list(datasets)) if datasets else 0}")
            except Exception as e:
                logger.debug(f"list_datasets: search_datasets() failed: {e}")

        if datasets is None:
            logger.warning("list_datasets: No method found to list datasets")
            return []

        # Convert to list of dicts
        result = []
        for d in datasets:
            result.append({
                "name": getattr(d, "name", str(d)),
                "description": getattr(d, "description", ""),
                "created_at": str(getattr(d, "created_at", "")),
            })

        logger.info(f"list_datasets: Found {len(result)} datasets")
        return result

    except Exception as e:
        logger.error(f"Failed to list datasets: {e}")
        return []
