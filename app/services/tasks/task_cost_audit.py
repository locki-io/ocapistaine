"""
Cost Audit Task (Njörðr)

Hourly audit of LLM costs. Logs daily and cumulative totals.
No idempotency check — runs every hour to capture trends.
"""

from app.services.cost import get_total_cost, get_daily_cost
from app.services.logging import TaskLogger

logger = TaskLogger("task_cost_audit")


def task_cost_audit(date_string: str = None) -> dict:
    """
    Log current cost totals for audit trail.

    Runs hourly. No lock needed — read-only.
    """
    total_usd, total_queries = get_total_cost()
    daily_usd = get_daily_cost()

    total_eur = total_usd * 0.92
    daily_eur = daily_usd * 0.92

    logger.info(
        f"COST_AUDIT | "
        f"daily=${daily_usd:.6f} ({daily_eur:.4f}€) | "
        f"total=${total_usd:.6f} ({total_eur:.4f}€) | "
        f"queries={total_queries}"
    )

    result = {
        "status": "success",
        "daily_usd": round(daily_usd, 6),
        "total_usd": round(total_usd, 6),
        "total_queries": total_queries,
        "daily_eur": round(daily_eur, 4),
        "total_eur": round(total_eur, 4),
    }

    logger.log_completed(status="success", items=total_queries)
    return result
