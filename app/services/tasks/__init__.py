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
