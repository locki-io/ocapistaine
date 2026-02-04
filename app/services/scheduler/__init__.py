"""
OCapistaine Scheduler Service

Production-grade task orchestration using APScheduler with Redis coordination.
Integrates with FastAPI lifespan for same-process deployment.

Features:
- Task orchestration with dependency management
- Distributed locking via Redis
- Idempotency via success keys (tasks run once per day)
- Cron-based scheduling for recurring tasks
- FastAPI lifespan integration

Usage:
    # In FastAPI main.py lifespan:
    from app.services.scheduler import start_scheduler, stop_scheduler

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await start_scheduler()
        yield
        await stop_scheduler()
"""

import asyncio
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.logging import TaskLogger

logger = TaskLogger("scheduler")

# Global state
scheduler: Optional[AsyncIOScheduler] = None
_loop: Optional[asyncio.AbstractEventLoop] = None

# Cron schedules
TASK_CHAIN_CRON = "*/30 6-23 * * *"  # Every 30 min, 6 AM - 11 PM
CRAWL_CRON = "0 3 * * *"  # Daily at 3 AM
OPIK_EXPERIMENT_CRON = "0 5 * * *"  # Daily at 5 AM


async def start_scheduler():
    """
    Initialize and start the scheduler.

    Called during FastAPI application startup via lifespan.
    Creates AsyncIOScheduler, registers jobs, and starts the scheduler.
    """
    global scheduler, _loop

    _loop = asyncio.get_event_loop()

    # Create scheduler with default in-memory job store
    # For production with multiple workers, consider Redis job store:
    # from apscheduler.jobstores.redis import RedisJobStore
    scheduler = AsyncIOScheduler(
        job_defaults={
            "coalesce": True,  # Combine multiple missed runs into one
            "max_instances": 2,  # Only one instance of each job at a time
            "misfire_grace_time": 300,  # 5 minutes grace for misfired jobs
        }
    )

    # Register scheduled jobs
    _register_jobs()

    scheduler.start()
    logger.info("Scheduler started")


async def stop_scheduler():
    """
    Gracefully stop the scheduler.

    Called during FastAPI application shutdown via lifespan.
    Waits for running jobs to complete before shutting down.
    """
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")


def _register_jobs():
    """
    Register all scheduled jobs with the scheduler.

    Job types:
    1. Task chain orchestrator - Runs every 7 min, manages daily task dependencies
    2. Firecrawl - Nightly document crawling at 3 AM
    3. Opik experiment - Daily evaluation experiments at 5 AM
    """
    from app.services.tasks import (
        task_opik_experiment,
        task_firecrawl,
    )

    # Daily task chain orchestrator
    # Runs every 7 minutes during active hours to check and execute pending tasks
    scheduler.add_job(
        func=orchestrate_task_chain,
        trigger=CronTrigger.from_crontab(TASK_CHAIN_CRON),
        id="orchestrate_task_chain",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Firecrawl - Nightly document crawling
    scheduler.add_job(
        func=task_firecrawl,
        trigger=CronTrigger.from_crontab(CRAWL_CRON),
        id="task_firecrawl",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Opik experiment - Daily evaluation run
    scheduler.add_job(
        func=task_opik_experiment,
        trigger=CronTrigger.from_crontab(OPIK_EXPERIMENT_CRON),
        id="task_opik_experiment",
        replace_existing=True,
        misfire_grace_time=600,
    )

    logger.info(f"Registered {len(scheduler.get_jobs())} scheduled jobs")


def orchestrate_task_chain():
    """
    Execute daily task chain with dependency management.

    Runs every 7 minutes during active hours (6 AM - 11 PM).
    Checks each task in the chain:
    - Skips if already completed today (success key exists)
    - Skips if dependencies not met
    - Executes if ready

    Task chain for OCapistaine:
    1. task_contributions_analysis - No dependencies

    Future tasks can be added with dependencies:
    - task_rag_indexing (depends on task_contributions_analysis)
    - task_report_generation (depends on task_rag_indexing)
    """
    from app.services.tasks import task_contributions_analysis
    from app.services.scheduler.utils import get_scheduler_redis

    today = datetime.now().strftime("%Y%m%d")
    l = get_scheduler_redis()

    # Define task chain with dependencies
    # Each task has: id, func, depends_on (list of task IDs that must complete first)
    task_chain = [
        {
            "id": "task_contributions_analysis",
            "func": task_contributions_analysis,
            "depends_on": [],
        },
        # Future tasks can be added here:
        # {
        #     "id": "task_rag_indexing",
        #     "func": task_rag_indexing,
        #     "depends_on": ["task_contributions_analysis"],
        # },
    ]

    for task in task_chain:
        task_id = task["id"]
        success_key = f"success:{task_id}:{today}"

        # Skip if already completed today
        if l.exists(success_key):
            continue

        # Check if all dependencies are met
        deps_met = all(
            l.exists(f"success:{dep}:{today}") for dep in task.get("depends_on", [])
        )

        if not deps_met:
            # Dependencies not yet completed, skip for now
            continue

        # Execute task
        try:
            result = task["func"](today)
            logger.info(
                f"orchestrate_task_chain: {task_id} -> {result.get('status', 'unknown')}"
            )
        except Exception as e:
            logger.error(f"orchestrate_task_chain: {task_id} failed: {e}")


def run_task_now(
    task_name: str,
    date_string: str = None,
    provider: str = None,
    enable_failover: bool = True,
    limit: int = 100,
    ollama_model: str = None,
    ollama_sleep: float = None,
    experiment_config: dict = None,
    source_config: dict = None,
) -> dict:
    """
    Manually trigger a task execution (for admin/debugging).

    Args:
        task_name: Name of the task to run
        date_string: Optional date override (YYYYMMDD format)
        provider: Optional provider name ("gemini", "claude", "mistral", "ollama")
        enable_failover: If True, try fallback providers on rate limit errors
        limit: Maximum contributions to process (for task_contributions_analysis)
        ollama_model: Specific Ollama model to use (e.g., "deepseek-r1:7b", "qwen3:4b")
        ollama_sleep: Seconds to sleep between Ollama validations (prevents CPU overload)
        experiment_config: Configuration for Opik experiments:
            - experiment_type: Type of experiment (e.g., "low_confidence_revalidation")
            - max_confidence: Maximum confidence threshold for selecting items
            - max_items: Maximum number of items to process
        source_config: Configuration for source filtering:
            - after_date: Only process contributions after this date (ISO format)
            - source: Filter by source ("Mockup Queue", "GitHub Issues", etc.)
            - limit: Maximum number of items to process

    Returns:
        dict: Task result

    Raises:
        ValueError: If task_name is not recognized
    """
    from app.services.tasks import (
        task_contributions_analysis,
        task_opik_experiment,
        task_firecrawl,
    )

    tasks = {
        "task_contributions_analysis": task_contributions_analysis,
        "task_opik_experiment": task_opik_experiment,
        "task_firecrawl": task_firecrawl,
    }

    if task_name not in tasks:
        raise ValueError(f"Unknown task: {task_name}. Available: {list(tasks.keys())}")

    if date_string is None:
        date_string = datetime.now().strftime("%Y%m%d")

    # Pass provider options to tasks that support it
    if task_name == "task_contributions_analysis":
        # Extract source config if provided
        src_config = source_config or {}
        task_limit = src_config.get("limit", limit)
        after_date = src_config.get("after_date")
        source = src_config.get("source")

        return tasks[task_name](
            date_string,
            provider=provider,
            enable_failover=enable_failover,
            limit=task_limit,
            ollama_model=ollama_model,
            ollama_sleep=ollama_sleep,
            after_date=after_date,
            source=source,
        )
    elif task_name == "task_opik_experiment":
        # Pass experiment configuration
        exp_config = experiment_config or {}
        return tasks[task_name](
            date_string,
            max_confidence=exp_config.get("max_confidence"),
            max_items=exp_config.get("max_items"),
            provider=provider or "ollama",
            model=ollama_model,
            ollama_sleep=ollama_sleep,
            experiment_type=exp_config.get("experiment_type", "low_confidence_revalidation"),
        )
    else:
        return tasks[task_name](date_string)


def get_scheduler_status() -> dict:
    """
    Get current scheduler status for monitoring.

    Returns:
        dict: Scheduler state including running status, job count, and job details
    """
    if scheduler is None:
        return {"status": "not_initialized", "job_count": 0, "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "next_run": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "trigger": str(job.trigger),
            }
        )

    return {
        "status": "running" if scheduler.running else "stopped",
        "job_count": len(jobs),
        "jobs": jobs,
    }


def get_task_history(date_string: str = None) -> list:
    """
    Get task execution history for a date.

    Args:
        date_string: Date in YYYYMMDD format. Defaults to today.

    Returns:
        list: Task status information including completion state and TTL
    """
    from app.services.scheduler.utils import get_scheduler_redis

    if date_string is None:
        date_string = datetime.now().strftime("%Y%m%d")

    l = get_scheduler_redis()
    tasks = [
        "task_contributions_analysis",
        "task_opik_experiment",
        "task_firecrawl",
    ]

    history = []
    for task in tasks:
        success_key = f"success:{task}:{date_string}"
        lock_key = f"lock:{task}:{date_string}"

        is_completed = l.exists(success_key)
        is_running = l.exists(lock_key)

        history.append(
            {
                "task": task,
                "date": date_string,
                "completed": is_completed,
                "running": is_running,
                "success_ttl": l.ttl(success_key) if is_completed else None,
                "lock_ttl": l.ttl(lock_key) if is_running else None,
            }
        )

    return history
