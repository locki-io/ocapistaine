"""
Prompt Sync Task

Synchronizes local prompts to Opik Prompt Library.
Runs daily at midnight to ensure Opik has the latest prompt versions.

Syncs:
- Individual prompts (forseti.*, autocontrib.*)
- Composite chat prompts (forseti-persona-*)
"""

from app.services.tasks import _task_boilerplate, TaskError, REDIS_SUCCESS_TTL


def task_prompt_sync(date_string: str = None) -> dict:
    """
    Sync all prompts to Opik Prompt Library.

    Workflow:
    1. Sync individual prompts (text type)
    2. Sync composite prompts (chat type)
    3. Log results

    Args:
        date_string: Date in YYYYMMDD format. Defaults to today.

    Returns:
        dict: Result with sync counts

    Raises:
        TaskError: If critical failure occurs during sync
    """
    redis_conn, lock_key, success_key, result, task_id, logger = _task_boilerplate(
        "task_prompt_sync", date_string
    )

    # Early exit if skipped
    if result["status"] == "skipped":
        return result

    try:
        from app.prompts.opik_sync import sync_all_prompts, sync_all_composites

        # Initialize counters
        result["individual_synced"] = 0
        result["individual_failed"] = 0
        result["composite_synced"] = 0
        result["composite_failed"] = 0
        result["prompts"] = []

        # Step 1: Sync individual prompts
        logger.log_progress("Syncing individual prompts")
        individual_result = sync_all_prompts()

        if individual_result.get("error"):
            result["warnings"].append(f"Individual sync warning: {individual_result['error']}")
        else:
            result["individual_synced"] = len(individual_result.get("synced", []))
            result["individual_failed"] = len(individual_result.get("failed", []))

            for item in individual_result.get("synced", []):
                result["prompts"].append({
                    "name": item["name"],
                    "type": "individual",
                    "commit": item.get("commit"),
                    "status": "synced",
                })

            for item in individual_result.get("failed", []):
                result["prompts"].append({
                    "name": item["name"],
                    "type": "individual",
                    "status": "failed",
                    "error": item.get("error"),
                })
                result["errors"].append(f"Individual: {item['name']} - {item.get('error')}")

        # Step 2: Sync composite prompts
        logger.log_progress("Syncing composite prompts")
        composite_result = sync_all_composites()

        if composite_result.get("error"):
            result["warnings"].append(f"Composite sync warning: {composite_result['error']}")
        else:
            result["composite_synced"] = len(composite_result.get("synced", []))
            result["composite_failed"] = len(composite_result.get("failed", []))

            for item in composite_result.get("synced", []):
                result["prompts"].append({
                    "name": item["name"],
                    "type": "composite",
                    "commit": item.get("commit"),
                    "components": item.get("components"),
                    "status": "synced",
                })

            for item in composite_result.get("failed", []):
                result["prompts"].append({
                    "name": item["name"],
                    "type": "composite",
                    "status": "failed",
                    "error": item.get("error"),
                })
                result["errors"].append(f"Composite: {item['name']} - {item.get('error')}")

        # Determine overall status
        total_synced = result["individual_synced"] + result["composite_synced"]
        total_failed = result["individual_failed"] + result["composite_failed"]

        if total_failed > 0 and total_synced == 0:
            result["status"] = "failed"
            logger.log_failed(
                error="All prompts failed to sync",
                individual_failed=result["individual_failed"],
                composite_failed=result["composite_failed"],
            )
        else:
            result["status"] = "success"
            redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)
            logger.log_completed(
                status="success",
                individual_synced=result["individual_synced"],
                individual_failed=result["individual_failed"],
                composite_synced=result["composite_synced"],
                composite_failed=result["composite_failed"],
            )

        return result

    except Exception as e:
        result["status"] = "failed"
        result["errors"].append(str(e))
        logger.log_failed(error=str(e), recoverable=False)
        raise TaskError("failed", str(e))

    finally:
        # Always release lock
        redis_conn.delete(lock_key)
