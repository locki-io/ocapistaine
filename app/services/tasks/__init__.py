"""
OCapistaine Task Registry

Task boilerplate and registry for scheduled tasks.
All tasks use consistent patterns for:
- Redis-based distributed locking
- Idempotency via success keys
- Standardized result dictionaries

Usage:
    from app.services.tasks import _task_boilerplate, TaskError

    def my_task(date_string: str = None) -> dict:
        l, lock_key, success_key, result, task_id = _task_boilerplate(
            "my_task", date_string
        )
        if result["status"] == "skipped":
            return result
        try:
            # Task logic here
            l.set(success_key, "completed", ex=86400)
            result["status"] = "success"
            return result
        finally:
            l.delete(lock_key)
"""

import os
import uuid
from datetime import datetime
from typing import Tuple, Dict, Any
import redis
from dotenv import load_dotenv

load_dotenv()

# Date format for task keys
DATE_FORMAT = "%Y%m%d"

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
) -> Tuple[redis.Redis, str, str, Dict[str, Any], str]:
    """
    Standard task initialization boilerplate.

    Handles common task setup:
    - Generates unique task ID
    - Creates lock and success keys
    - Checks for already-completed or currently-running tasks
    - Acquires distributed lock

    Args:
        task_name: Full task identifier (e.g., "task_contributions_analysis")
        date_string: Date in DATE_FORMAT (e.g., "20251103"). Defaults to today.
        skip_success_check: If True, skip success key check (for recurring tasks).
                           Default: False.

    Returns:
        tuple: (redis_conn, lock_key, success_key, result_dict, task_id)

    Example:
        l, lock_key, success_key, result, task_id = _task_boilerplate(
            "task_contributions_analysis", date_string
        )

        if result["status"] == "skipped":
            return result  # Already completed or running

        try:
            # Your task logic here
            result["status"] = "success"
            l.set(success_key, "completed", ex=86400)
            return result
        except Exception as e:
            result["status"] = "failed"
            result["errors"].append(str(e))
            raise TaskError("failed", str(e))
        finally:
            l.delete(lock_key)  # Always release lock
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
    l = get_scheduler_redis()

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
    if not skip_success_check and l.exists(success_key):
        result["status"] = "skipped"
        result["reason"] = "already_completed"
        print(f"Skipping {task_name}: already completed for {date_string}")
        return l, lock_key, success_key, result, task_id

    # Try to acquire distributed lock
    acquired = l.set(lock_key, task_id, ex=REDIS_LOCK_TIMEOUT, nx=True)
    if not acquired:
        result["status"] = "skipped"
        result["reason"] = "lock_held"
        print(f"Skipping {task_name}: another instance is running for {date_string}")
        return l, lock_key, success_key, result, task_id

    print(f"Starting {task_name} (task_id={task_id}, date={date_string}, pid={os.getpid()})")
    return l, lock_key, success_key, result, task_id


# Import all task functions AFTER defining utilities to avoid circular imports
from app.services.tasks.task_contributions_analysis import task_contributions_analysis
from app.services.tasks.task_opik_experiment import task_opik_experiment
from app.services.tasks.task_firecrawl import task_firecrawl

__all__ = [
    # Utilities
    "TaskError",
    "_task_boilerplate",
    "DATE_FORMAT",
    "REDIS_LOCK_TIMEOUT",
    "REDIS_SUCCESS_TTL",
    # Tasks
    "task_contributions_analysis",
    "task_opik_experiment",
    "task_firecrawl",
]
