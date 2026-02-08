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
from dotenv import load_dotenv

load_dotenv()


# Global connection pool
_redis_pool: Optional[redis.ConnectionPool] = None


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


# Key prefix for app data (separates from scheduler keys in shared db=0)
APP_KEY_PREFIX = "app:"


def get_redis_pool() -> redis.ConnectionPool:
    """
    Get or create Redis connection pool.

    Supports UPSTASH_REDIS_REST_URL or REDIS_HOST/PORT/PASSWORD.
    Uses db=0 for cloud compatibility (Upstash free tier).
    """
    global _redis_pool

    if _redis_pool is None:
        host, port, password, use_ssl = _get_redis_config()
        # Default to db=0 for cloud compatibility (Upstash only supports db=0)
        redis_db = os.getenv("REDIS_DB", "0")

        # Build URL with optional password
        if password:
            redis_url = f"rediss://default:{password}@{host}:{port}/{redis_db}" if use_ssl else f"redis://default:{password}@{host}:{port}/{redis_db}"
        else:
            redis_url = f"redis://{host}:{port}/{redis_db}"

        _redis_pool = redis.ConnectionPool.from_url(
            redis_url,
            decode_responses=True,
            max_connections=10,
        )

    return _redis_pool


def app_key(key: str) -> str:
    """Prefix a key for app namespace. Use for all app data keys."""
    return f"{APP_KEY_PREFIX}{key}"


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

    SESSION = 86400  # 24 hours
    CHAT = 604800  # 7 days
    DOCUMENT = 3600  # 1 hour
    RATE_LIMIT = 60  # 1 minute


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
