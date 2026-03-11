"""
Njörðr — Cost Accumulation Service

Persistent cost counters in Redis (no TTL).
Tracks session cost, daily cost, and lifetime total.
"""

from datetime import date

from app.data.redis_client import get_redis_connection, app_key


# Redis keys (under app: namespace, no TTL)
_KEY_TOTAL = app_key("cost:total_usd")
_KEY_DAILY = "app:cost:daily:{date}"
_KEY_QUERIES = app_key("cost:total_queries")


def record_cost(cost_usd: float, model: str = "") -> None:
    """
    Record a query cost. Called after each LLM call.

    Increments:
    - app:cost:total_usd (lifetime, no TTL)
    - app:cost:daily:{YYYY-MM-DD} (daily, no TTL — kept for trends)
    - app:cost:total_queries (lifetime query count)
    """
    if cost_usd is None or cost_usd <= 0:
        return
    try:
        r = get_redis_connection()
        today = date.today().isoformat()
        pipe = r.pipeline()
        pipe.incrbyfloat(_KEY_TOTAL, cost_usd)
        pipe.incrbyfloat(_KEY_DAILY.format(date=today), cost_usd)
        pipe.incr(_KEY_QUERIES)
        pipe.execute()
    except Exception:
        pass  # Cost tracking must never break the app


def get_total_cost() -> tuple[float, int]:
    """
    Get lifetime cost and query count.

    Returns:
        (total_usd, total_queries)
    """
    try:
        r = get_redis_connection()
        total = r.get(_KEY_TOTAL)
        queries = r.get(_KEY_QUERIES)
        return float(total or 0), int(queries or 0)
    except Exception:
        return 0.0, 0


def get_daily_cost(day: str | None = None) -> float:
    """Get cost for a specific day (default: today)."""
    try:
        r = get_redis_connection()
        day = day or date.today().isoformat()
        val = r.get(_KEY_DAILY.format(date=day))
        return float(val or 0)
    except Exception:
        return 0.0
