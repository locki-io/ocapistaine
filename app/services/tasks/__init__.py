"""
OCapistaine Task Registry

Task boilerplate and registry for scheduled tasks.
All tasks use consistent patterns for:
- Redis-based distributed locking
- Idempotency via success keys
- Standardized result dictionaries
- Structured logging via TaskLogger

Usage:
    from app.services.tasks import _task_boilerplate, TaskError

    def my_task(date_string: str = None) -> dict:
        redis_conn, lock_key, success_key, result, task_id, logger = _task_boilerplate(
            "my_task", date_string
        )
        if result["status"] == "skipped":
            return result
        try:
            # Task logic here
            redis_conn.set(success_key, "completed", ex=86400)
            result["status"] = "success"
            logger.log_completed(status="success", items_processed=10)
            return result
        except Exception as e:
            logger.log_failed(error=str(e))
            raise TaskError("failed", str(e))
        finally:
            redis_conn.delete(lock_key)
"""

import os
import uuid
from datetime import datetime
from typing import Tuple, Dict, Any
import redis
from dotenv import load_dotenv

from app.services.logging import TaskLogger

load_dotenv()

# Date format for task keys
DATE_FORMAT = "%Y%m%d"

# =============================================================================
# Agent Feature Registry for Opik Optimization
# =============================================================================
# Maps experiment types to agent features (spans).
# Each feature that logs Correctness feedback can be optimized.
#
# Structure:
#   experiment_type -> {
#       "agent": agent name,
#       "feature": feature/span name,
#       "dataset_prefix": prefix for Opik dataset names,
#       "description": human-readable description
#   }
#
# To add a new optimizable feature:
# 1. Ensure the feature logs Correctness feedback via tracer.log_span_feedback()
# 2. Add metadata "added_to_dataset: False" to the span
# 3. Register the feature in AGENT_FEATURE_REGISTRY below

AGENT_FEATURE_REGISTRY: dict[str, dict] = {
    # Forseti Agent Features
    "charter_optimization": {
        "agent": "forseti",
        "feature": "charter_validation",  # span name
        "prompt_key": "forseti.charter_validation",  # key in app.prompts registry
        "dataset_prefix": "charter-optimization",
        "description": "Charter compliance validation - checks contributions against charter rules",
    },
    "category_optimization": {
        "agent": "forseti",
        "feature": "category_classification",  # span name
        "prompt_key": "forseti.category_classification",  # key in app.prompts registry
        "dataset_prefix": "category-optimization",
        "description": "Category classification - assigns contributions to one of 7 categories",
    },
    # Future: Forseti wording_correction (when Correctness feedback is added)
    # "wording_optimization": {
    #     "agent": "forseti",
    #     "feature": "wording_correction",
    #     "prompt_key": "forseti.wording_correction",
    #     "dataset_prefix": "wording-optimization",
    #     "description": "Wording suggestions - improves contribution text",
    # },
    #
    # Future: Other agents
    # "draft_optimization": {
    #     "agent": "contribution_assistant",
    #     "feature": "draft_generation",
    #     "prompt_key": "autocontrib.draft_fr",
    #     "dataset_prefix": "draft-optimization",
    #     "description": "Draft generation quality for auto-contribution",
    # },
}


def get_optimizable_features() -> list[str]:
    """Get list of all experiment types that can be optimized."""
    return list(AGENT_FEATURE_REGISTRY.keys())


def get_feature_config(experiment_type: str) -> dict | None:
    """Get configuration for an experiment type."""
    return AGENT_FEATURE_REGISTRY.get(experiment_type)


def get_feature_prompt(experiment_type: str) -> tuple[str | None, dict | None]:
    """
    Get the prompt template and metadata for a feature.

    Args:
        experiment_type: The experiment type (e.g., "charter_optimization")

    Returns:
        tuple: (prompt_template, prompt_metadata) or (None, None) if not found
    """
    config = get_feature_config(experiment_type)
    if not config:
        return None, None

    prompt_key = config.get("prompt_key")
    if not prompt_key:
        return None, None

    try:
        from app.prompts import get_prompt, get_registry

        template = get_prompt(prompt_key)
        registry = get_registry()
        info = registry.get_prompt(prompt_key)
        metadata = {
            "key": prompt_key,
            "source": getattr(info, "source", "local"),
            "version": getattr(info, "version", "1.0.0"),
            "variables": getattr(info, "variables", []),
        }
        return template, metadata
    except Exception:
        return None, None


def get_features_by_agent(agent_name: str) -> list[dict]:
    """
    Get all optimizable features for a specific agent.

    Args:
        agent_name: The agent name (e.g., "forseti")

    Returns:
        list: List of feature configs for the agent
    """
    return [
        {"experiment_type": exp_type, **config}
        for exp_type, config in AGENT_FEATURE_REGISTRY.items()
        if config.get("agent") == agent_name
    ]

# Redis configuration
REDIS_DB_SCHEDULER = 6  # Dedicated Redis DB for scheduler

# TTL Constants
REDIS_LOCK_TIMEOUT = 300  # 5 minutes - lock expires if task hangs
REDIS_SUCCESS_TTL = 86400  # 24 hours - task won't re-run same day


class TaskError(Exception):
    """
    Custom exception for task failures.

    Provides structured error information for task monitoring and alerting.

    Attributes:
        status: Error status code (e.g., "failed", "timeout", "dependency_error")
        message: Human-readable error description
    """

    def __init__(self, status: str, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def _task_boilerplate(
    task_name: str,
    date_string: str = None,
    skip_success_check: bool = False,
) -> Tuple[redis.Redis, str, str, Dict[str, Any], str, TaskLogger]:
    """
    Standard task initialization boilerplate.

    Handles common task setup:
    - Generates unique task ID
    - Creates lock and success keys
    - Checks for already-completed or currently-running tasks
    - Acquires distributed lock
    - Initializes TaskLogger for structured logging

    Args:
        task_name: Full task identifier (e.g., "task_contributions_analysis")
        date_string: Date in DATE_FORMAT (e.g., "20251103"). Defaults to today.
        skip_success_check: If True, skip success key check (for recurring tasks).
                           Default: False.

    Returns:
        tuple: (redis_conn, lock_key, success_key, result_dict, task_id, logger)

    Example:
        redis_conn, lock_key, success_key, result, task_id, logger = _task_boilerplate(
            "task_contributions_analysis", date_string
        )

        if result["status"] == "skipped":
            return result  # Already completed or running

        try:
            # Your task logic here
            result["status"] = "success"
            redis_conn.set(success_key, "completed", ex=86400)
            logger.log_completed(status="success", items=10)
            return result
        except Exception as e:
            result["status"] = "failed"
            result["errors"].append(str(e))
            logger.log_failed(error=str(e))
            raise TaskError("failed", str(e))
        finally:
            redis_conn.delete(lock_key)  # Always release lock
    """
    from app.services.scheduler.utils import get_scheduler_redis

    # Default to today if no date provided
    if date_string is None:
        date_string = datetime.now().strftime(DATE_FORMAT)

    # Generate unique task execution ID
    task_id = str(uuid.uuid4())[:8]

    # Key patterns for distributed coordination
    lock_key = f"lock:{task_name}:{date_string}"
    success_key = f"success:{task_name}:{date_string}"

    # Get scheduler Redis connection
    redis_conn = get_scheduler_redis()

    # Initialize TaskLogger for this task
    logger = TaskLogger(task_name)

    # Initialize result dictionary
    result = {
        "task": task_name,
        "date": date_string,
        "task_id": task_id,
        "status": "pending",
        "errors": [],
        "warnings": [],
        "reason": None,
    }

    # Check if task already completed today (unless skipped for recurring tasks)
    if not skip_success_check and redis_conn.exists(success_key):
        result["status"] = "skipped"
        result["reason"] = "already_completed"
        logger.log_skipped(reason="already_completed", date_string=date_string, task_id=task_id)
        return redis_conn, lock_key, success_key, result, task_id, logger

    # Try to acquire distributed lock
    acquired = redis_conn.set(lock_key, task_id, ex=REDIS_LOCK_TIMEOUT, nx=True)
    if not acquired:
        result["status"] = "skipped"
        result["reason"] = "lock_held"
        logger.log_skipped(reason="lock_held", date_string=date_string, task_id=task_id)
        return redis_conn, lock_key, success_key, result, task_id, logger

    logger.log_start(task_id=task_id, date_string=date_string, pid=os.getpid())
    return redis_conn, lock_key, success_key, result, task_id, logger


# Import all task functions AFTER defining utilities to avoid circular imports
from app.services.tasks.task_contributions_analysis import task_contributions_analysis
from app.services.tasks.task_opik_experiment import task_opik_experiment
from app.services.tasks.task_opik_evaluate import task_opik_evaluate
from app.services.tasks.task_firecrawl import task_firecrawl
from app.services.tasks.task_prompt_sync import task_prompt_sync
from app.services.tasks.task_audierne_docs import task_audierne_docs

__all__ = [
    # Utilities
    "TaskError",
    "_task_boilerplate",
    "DATE_FORMAT",
    "REDIS_LOCK_TIMEOUT",
    "REDIS_SUCCESS_TTL",
    # Agent Feature Registry
    "AGENT_FEATURE_REGISTRY",
    "get_optimizable_features",
    "get_feature_config",
    "get_feature_prompt",
    "get_features_by_agent",
    # Tasks
    "task_contributions_analysis",
    "task_opik_experiment",
    "task_opik_evaluate",  # Creates dataset + runs evaluate()
    "task_firecrawl",
    "task_prompt_sync",  # Daily prompt sync to Opik
    "task_audierne_docs",  # Audierne docs processing (dev)
]
