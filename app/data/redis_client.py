# redis_client.py
"""
Redis Client - Data Access Layer

Single Redis connection for all caching needs.
Handles sessions, chat history, and document cache.
"""

import os
import redis
from typing import Optional
from contextlib import contextmanager

# Global connection pool
_redis_pool: Optional[redis.ConnectionPool] = None


def get_redis_pool() -> redis.ConnectionPool:
    """
    Get or create Redis connection pool.

    Uses REDIS_URL from environment or defaults to localhost.
    """
    global _redis_pool

    if _redis_pool is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_pool = redis.ConnectionPool.from_url(
            redis_url,
            decode_responses=True,
            max_connections=10,
        )

    return _redis_pool


def get_redis_connection() -> redis.Redis:
    """
    Get a Redis connection from the pool.

    Returns:
        redis.Redis: Redis client instance
    """
    pool = get_redis_pool()
    return redis.Redis(connection_pool=pool)


@contextmanager
def redis_connection():
    """
    Context manager for Redis connections.

    Usage:
        with redis_connection() as r:
            r.set("key", "value")
    """
    r = get_redis_connection()
    try:
        yield r
    finally:
        pass  # Connection returns to pool automatically


# Key prefixes for organization
class RedisKeys:
    """Redis key patterns."""

    SESSION = "session:{user_id}"
    CHAT = "chat:{user_id}:{thread_id}"
    DOCUMENT = "document:{doc_id}"
    RATE_LIMIT = "rate_limit:{user_id}"
    CRAWL_STATUS = "crawl:{source}"

    @staticmethod
    def session(user_id: str) -> str:
        return f"session:{user_id}"

    @staticmethod
    def chat(user_id: str, thread_id: str) -> str:
        return f"chat:{user_id}:{thread_id}"

    @staticmethod
    def document(doc_id: str) -> str:
        return f"document:{doc_id}"

    @staticmethod
    def rate_limit(user_id: str) -> str:
        return f"rate_limit:{user_id}"


# TTL constants (in seconds)
class TTL:
    """Time-to-live constants for Redis keys."""

    SESSION = 86400      # 24 hours
    CHAT = 604800        # 7 days
    DOCUMENT = 3600      # 1 hour
    RATE_LIMIT = 60      # 1 minute


def health_check() -> bool:
    """
    Check Redis connection health.

    Returns:
        bool: True if Redis is reachable
    """
    try:
        r = get_redis_connection()
        return r.ping()
    except redis.ConnectionError:
        return False
