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

from app.services.logging import get_logger

load_dotenv()

logger = get_logger("tasks")

# Dedicated Redis DB for scheduler locks and success keys
REDIS_DB_SCHEDULER = 6


def _get_redis_config() -> tuple[str, int, str | None, bool]:
    """
    Get Redis connection config from environment.

    Supports multiple env var formats:
    - REDIS_HOST + REDIS_PORT + REDIS_PASSWORD (standard)
    - UPSTASH_REDIS_REST_URL (auto-parse Upstash URL)

    Returns:
        Tuple of (host, port, password, use_ssl)
    """
    # Check for Upstash URL first
    upstash_url = os.getenv("UPSTASH_REDIS_REST_URL", "")
    if upstash_url:
        # Parse: https://xxx.upstash.io -> xxx.upstash.io
        host = upstash_url.replace("https://", "").replace("http://", "").rstrip("/")
        password = os.getenv("REDIS_PASSWORD") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
        return host, 6379, password, True  # Upstash always uses SSL

    # Standard config
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_password = os.getenv("REDIS_PASSWORD", "") or None
    use_ssl = "upstash" in redis_host.lower()

    return redis_host, redis_port, redis_password, use_ssl


def get_scheduler_redis() -> redis.Redis:
    """
    Get Redis connection for scheduler locks and success keys.

    Uses dedicated database (db=6) to isolate scheduler state from app data.
    Supports Upstash and other cloud Redis providers with password auth.

    Returns:
        redis.Redis: Redis client connected to scheduler database
    """
    host, port, password, use_ssl = _get_redis_config()

    return redis.Redis(
        host=host,
        port=port,
        password=password,
        db=REDIS_DB_SCHEDULER,
        decode_responses=True,
        ssl=use_ssl,
        ssl_cert_reqs=None if use_ssl else None,
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
        pass  # Connection is not pooled, will close automatically
