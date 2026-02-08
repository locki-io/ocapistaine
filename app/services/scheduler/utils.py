"""
Scheduler utility functions.

This module contains shared utilities used by both the scheduler and task modules.
Extracted to avoid circular imports between app.services.scheduler and app.services.tasks.
"""

import os
from contextlib import contextmanager

from app.services.logging import get_logger
from app.data.redis_client import get_redis_config, get_redis_connection

logger = get_logger("tasks")

# Scheduler key prefix (separates from app data in shared db)
SCHED_KEY_PREFIX = "sched:"


def get_scheduler_redis():
    """
    Get Redis connection for scheduler locks and success keys.

    Uses the shared connection pool from redis_client.
    Keys are prefixed with 'sched:' to separate from app data.

    Returns:
        redis.Redis: Redis client from shared pool
    """
    return get_redis_connection()


def sched_key(key: str) -> str:
    """Prefix a key for scheduler namespace. Use for all scheduler keys."""
    return f"{SCHED_KEY_PREFIX}{key}"


def normalize_timestamp(ts: int | float) -> int:
    """
    Normalize timestamp to seconds.

    Converts millisecond timestamps to seconds if necessary.
    Useful for handling timestamps from various APIs.

    Args:
        ts: Timestamp (in seconds or milliseconds)

    Returns:
        int: Timestamp in seconds
    """
    ts = float(ts)
    if ts > 1e12:  # Greater than ~Sat Sep 09 2001 in ms
        ts = ts / 1000  # Convert from ms to seconds
    return int(ts)


def clear_old_jobs(scheduler, prefix: str = "task_") -> int:
    """
    Remove stale jobs with given prefix from the scheduler.

    Args:
        scheduler: APScheduler instance
        prefix: Job ID prefix to match (default: "task_")

    Returns:
        int: Number of jobs removed
    """
    removed = 0
    try:
        jobs = scheduler.get_jobs()
        for job in jobs:
            if job.id.startswith(prefix) and job.next_run_time is None:
                scheduler.remove_job(job.id)
                removed += 1
    except Exception as e:
        logger.error(f"Error clearing old jobs: {e}")
    return removed


def clear_all_jobs(scheduler) -> int:
    """
    Remove all existing jobs from the scheduler.

    Use with caution - typically only for testing or reset scenarios.

    Args:
        scheduler: APScheduler instance

    Returns:
        int: Number of jobs removed
    """
    removed = 0
    try:
        jobs = scheduler.get_jobs()
        for job in jobs:
            scheduler.remove_job(job.id)
            removed += 1
    except Exception as e:
        logger.error(f"Error clearing jobs: {e}")
    return removed


@contextmanager
def scheduler_redis_connection():
    """
    Context manager for scheduler Redis connections.

    Usage:
        with scheduler_redis_connection() as r:
            r.set("key", "value", ex=300)
    """
    r = get_scheduler_redis()
    try:
        yield r
    finally:
        pass  # Connection returns to pool automatically
