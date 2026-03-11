"""
Prompt Sync Task

Bidirectional sync with Opik Prompt Library.
Runs daily at midnight to ensure Opik and local prompts stay in sync.

Steps:
0. Pull optimized composites from Opik (update local JSON)
1. Push individual prompts (forseti.*, autocontrib.*)
2. Push composite chat prompts (forseti-persona-*)
"""

from app.services.tasks import _task_boilerplate, TaskError, REDIS_SUCCESS_TTL


def task_prompt_sync(date_string: str = None) -> dict:
    """
    Sync all prompts to Opik Prompt Library (bidirectional).

    Workflow:
    0. Pull optimized composites from Opik (update locals)
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
        from app.prompts.opik_sync import (
            sync_all_prompts,
            sync_all_composites,
            pull_all_composites,
        )

        # Initialize counters
        result["pull_changed"] = 0
        result["pull_failed"] = 0
        result["individual_synced"] = 0
        result["individual_failed"] = 0
        result["composite_synced"] = 0
        result["composite_failed"] = 0
        result["prompts"] = []

        # Step 0: Pull optimized composites from Opik (before pushing)
        logger.log_progress("Pulling optimized composites from Opik")
        pull_result = pull_all_composites()

        if pull_result.get("error"):
            result["warnings"].append(f"Pull warning: {pull_result['error']}")
        else:
            for item in pull_result.get("pulled", []):
                changed = item.get("changed", [])
                if changed:
                    result["pull_changed"] += len(changed)
                for w in item.get("warnings", []):
                    result["warnings"].append(f"Pull: {w}")
            result["pull_failed"] = len(pull_result.get("failed", []))

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
                pull_changed=result["pull_changed"],
                pull_failed=result["pull_failed"],
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
