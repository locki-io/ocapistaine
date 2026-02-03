"""
Scheduler utility functions.

This module contains shared utilities used by both the scheduler and task modules.
Extracted to avoid circular imports between app.services.scheduler and app.services.tasks.
"""

import os
import redis
from typing import Optional
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# Dedicated Redis DB for scheduler locks and success keys
REDIS_DB_SCHEDULER = 6


def get_scheduler_redis() -> redis.Redis:
    """
    Get Redis connection for scheduler locks and success keys.

    Uses dedicated database (db=6) to isolate scheduler state from app data.

    Returns:
        redis.Redis: Redis client connected to scheduler database
    """
    redis_port = os.getenv("REDIS_PORT", "6379")
    return redis.Redis(
        host="localhost",
        port=int(redis_port),
        db=REDIS_DB_SCHEDULER,
        decode_responses=True,
    )


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
        print(f"Error clearing old jobs: {e}")
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
        print(f"Error clearing jobs: {e}")
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
        pass  # Connection is not pooled, will close automatically
