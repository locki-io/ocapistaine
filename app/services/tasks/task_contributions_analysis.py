"""
Daily Contributions Analysis Task

Analyzes and validates pending citizen contributions from various sources:
- MockupStorage (Redis, app: prefix) - ValidationRecords awaiting Forseti analysis
- GitHub issues (audierne2026/participons) - Fetched via N8N webhook
- Facebook/Email submissions (via Vaettir) - Future integration

Uses Forseti agent for validation against contribution charter.
Results are stored back in MockupStorage for Opik dataset export.
"""

import asyncio
import time
from datetime import datetime

from app.services.tasks import _task_boilerplate, TaskError, REDIS_SUCCESS_TTL

# Default sleep time between Ollama validations (seconds)
# Prevents CPU/GPU overload on local hardware
OLLAMA_DEFAULT_SLEEP_SECONDS = 2.0


def _get_session_provider() -> str:
    """Get default provider from session settings or fallback."""
    try:
        from app.services.session import get_current_provider

        return get_current_provider()
    except Exception:
        return "ollama"


def _github_issue_to_validation_record(issue: dict):
    """
    Convert a GitHub issue dict to a ValidationRecord.

    Args:
        issue: GitHub issue from N8N webhook

    Returns:
        ValidationRecord instance
    """
    from app.mockup.storage import ValidationRecord
    from datetime import datetime
    import uuid

    # Extract category from labels or issue data
    category = issue.get("category", "")

    # Build body from issue body
    body = issue.get("body", "")

    # Get parsed date
    parsed_date = issue.get("parsed_date")
    date_str = parsed_date.isoformat() if parsed_date else datetime.now().strftime("%Y-%m-%d")

    # Generate unique ID for the record
    github_id = issue.get("id", 0)
    record_id = f"github-{github_id}-{uuid.uuid4().hex[:8]}"

    # Create record with all fields properly set
    record = ValidationRecord(
        id=record_id,
        date=date_str,
        title=issue.get("title", ""),
        body=body,
        category=category,
        constat_factuel=body,  # Use full body as constat
        idees_ameliorations="",  # GitHub issues don't have separate fields
        source="github",
        confidence=0.0,  # Mark as needing validation
        is_valid=True,  # Default, will be updated by Forseti
        github_issue_id=github_id,
        github_url=issue.get("html_url"),
        github_user=issue.get("user"),
        has_conforme_charte=issue.get("has_conforme_charte", False),
    )

    return record


def task_contributions_analysis(
    date_string: str = None,
    provider: str = None,
    enable_failover: bool = True,
    limit: int = 100,
    ollama_model: str = None,
    ollama_sleep: float = None,
    after_date: str = None,
    source: str = None,
) -> dict:
    """
    Analyze and validate pending contributions from MockupStorage.

    Workflow:
    1. Fetch latest validations from MockupStorage
    2. Filter for records needing validation (confidence == 0)
    3. Apply date filter if specified
    4. Run Forseti validation on each contribution
    5. Update records in MockupStorage with results
    6. Mark task completed via sched: prefix key

    Args:
        date_string: Date in YYYYMMDD format. Defaults to today.
        provider: LLM provider name ("gemini", "claude", "mistral", "ollama").
        enable_failover: If True, try fallback providers on rate limit errors.
        limit: Maximum number of contributions to process (default 100).
        ollama_model: Specific Ollama model (e.g., "deepseek-r1:7b", "qwen3:4b").
        ollama_sleep: Seconds to sleep between Ollama validations (default 2.0).
                      Prevents CPU/GPU overload on local hardware.
        after_date: Only process contributions after this date (ISO format: YYYY-MM-DD).
        source: Filter by source ("mockup", "github", or None for all).

    Returns:
        dict: Result with status, counts, and any errors

    Raises:
        TaskError: If critical failure occurs during processing
    """
    redis_conn, lock_key, success_key, result, task_id, logger = _task_boilerplate(
        "task_contributions_analysis", date_string
    )

    # Store provider config in result
    result["provider"] = provider
    result["enable_failover"] = enable_failover
    result["limit"] = limit
    result["ollama_model"] = ollama_model
    result["ollama_sleep"] = ollama_sleep if ollama_sleep is not None else OLLAMA_DEFAULT_SLEEP_SECONDS
    result["after_date"] = after_date
    result["source_filter"] = source

    # Early exit if skipped (already completed or lock held)
    if result["status"] == "skipped":
        return result

    try:
        # Initialize counters
        result["contributions_fetched"] = 0
        result["contributions_validated"] = 0
        result["contributions_approved"] = 0
        result["contributions_flagged"] = 0
        result["contributions_skipped"] = 0
        result["github_issues_processed"] = 0

        # Fetch contributions based on source selection
        from app.mockup.storage import get_storage
        from datetime import date, timedelta

        storage = get_storage()
        records = []
        source_lower = (source or "mockup queue").lower()

        # Fetch from Mockup Queue if selected or "both"
        if source_lower in ("mockup queue", "mockup", "both", "all", ""):
            logger.log_progress("Fetching from Mockup Queue")

            # Try latest validations first (get more than limit to allow for filtering)
            mockup_records = storage.get_latest_validations(limit=1000)

            # If latest is empty, check recent date indexes (last 7 days)
            if not mockup_records:
                logger.log_progress("Checking date indexes (latest empty)")
                all_records = []
                for days_ago in range(7):
                    check_date = date.today() - timedelta(days=days_ago)
                    date_records = storage.get_validations_by_date(check_date.isoformat())
                    all_records.extend(date_records)
                mockup_records = all_records

            # Filter mockup records to only include mockup sources
            mockup_records = [
                r for r in mockup_records
                if r.source in ("mock", "derived", "input", "framaforms")
            ]
            records.extend(mockup_records)
            logger.log_progress(f"Mockup Queue: {len(mockup_records)} records")

        # Fetch from GitHub Issues if selected or "both"
        if source_lower in ("github issues", "github", "both", "all"):
            logger.log_progress("Fetching from GitHub Issues")

            from app.services.github_issues import get_issues_for_validation

            github_issues = get_issues_for_validation(
                after_date=after_date,
                limit=limit,
            )

            # Convert GitHub issues to ValidationRecord format
            github_records = [
                _github_issue_to_validation_record(issue)
                for issue in github_issues
            ]
            records.extend(github_records)
            result["github_issues_fetched"] = len(github_records)
            logger.log_progress(f"GitHub Issues: {len(github_records)} records")

        # Apply date filter if specified (for mockup records that don't have pre-filtering)
        if after_date:
            before_count = len(records)
            records = [r for r in records if r.date and r.date >= after_date]
            logger.log_progress(
                f"Date filter applied: {before_count} -> {len(records)} (after {after_date})"
            )

        result["contributions_fetched"] = len(records)

        if not records:
            result["status"] = "success"
            result["reason"] = "no_contributions_to_process"
            redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)
            logger.log_completed(status="no_work", reason="no_contributions_to_process")
            return result

        # Filter for records needing validation (confidence == 0 means not yet validated)
        pending_records = [r for r in records if r.confidence == 0.0][:limit]

        if not pending_records:
            result["status"] = "success"
            result["reason"] = "all_contributions_already_validated"
            result["contributions_skipped"] = len(records)
            redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)
            logger.log_completed(
                status="no_work",
                reason="all_already_validated",
                skipped=len(records),
            )
            return result

        # Initialize Forseti agent with provider selection and failover
        from app.agents.forseti import ForsetiAgent

        # Failover provider order (session provider first, then ollama, then cloud)
        session_provider = _get_session_provider()
        PROVIDER_FAILOVER_ORDER = [session_provider, "ollama", "gemini", "claude", "mistral"]
        # Remove duplicates while preserving order
        PROVIDER_FAILOVER_ORDER = list(dict.fromkeys(PROVIDER_FAILOVER_ORDER))

        def get_providers_to_try():
            """Get list of providers to try based on settings."""
            providers = []
            if provider:
                providers.append(provider)
            if enable_failover:
                for p in PROVIDER_FAILOVER_ORDER:
                    if p not in providers:
                        providers.append(p)
            elif not provider:
                # No provider specified and no failover, use session provider
                providers.append(session_provider)
            return providers

        providers_to_try = get_providers_to_try()
        result["providers_tried"] = []

        # Process each pending contribution
        updated_records = []
        for idx, record in enumerate(pending_records):
            validation_result = None
            last_error = None

            for try_provider in providers_to_try:
                try:
                    # Build title and body from Framaforms fields
                    title = record.title or record.category or "Contribution"
                    body = _build_body(record.constat_factuel, record.idees_ameliorations)

                    # Create agent with specific provider
                    # For Ollama, use the specified model if provided
                    if try_provider == "ollama" and ollama_model:
                        from app.providers import OllamaProvider

                        ollama_provider = OllamaProvider(model=ollama_model)
                        forseti = ForsetiAgent(provider=ollama_provider)
                        provider_info = f"ollama:{ollama_model}"
                    else:
                        forseti = ForsetiAgent(provider_name=try_provider)
                        provider_info = try_provider

                    if provider_info not in result["providers_tried"]:
                        result["providers_tried"].append(provider_info)

                    # Run Forseti validation
                    validation_result = asyncio.run(
                        forseti.validate(
                            title=title,
                            body=body,
                            category=record.category,
                        )
                    )

                    # Success - record which provider worked
                    record.provider = provider_info
                    break  # Exit provider loop on success

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    # Check if this is a rate limit error that warrants failover
                    is_rate_limit = any(
                        term in error_str
                        for term in ["rate", "limit", "quota", "429", "exhausted"]
                    )

                    if is_rate_limit and enable_failover:
                        # Find next provider index
                        current_idx = providers_to_try.index(try_provider)
                        next_provider = (
                            providers_to_try[current_idx + 1]
                            if current_idx + 1 < len(providers_to_try)
                            else "none"
                        )
                        logger.log_provider_failover(
                            from_provider=try_provider,
                            to_provider=next_provider,
                            reason="rate_limit",
                        )
                        continue  # Try next provider
                    else:
                        # Non-rate-limit error, don't failover
                        break

            if validation_result:
                # Update record with validation results
                record.is_valid = validation_result.is_valid
                record.violations = validation_result.violations
                record.encouraged_aspects = validation_result.encouraged_aspects
                record.confidence = validation_result.confidence
                record.reasoning = validation_result.reasoning
                record.suggested_category = validation_result.category
                record.timestamp = datetime.now().isoformat()

                updated_records.append(record)

                # Log individual validation result
                logger.log_validation_result(
                    record_id=record.id,
                    is_valid=validation_result.is_valid,
                    provider=record.provider,
                    confidence=validation_result.confidence,
                )

                if validation_result.is_valid:
                    result["contributions_approved"] += 1
                else:
                    result["contributions_flagged"] += 1

                result["contributions_validated"] += 1

                # Handle GitHub-specific actions (notify N8N to add label)
                if record.source == "github" and hasattr(record, "github_issue_id"):
                    result["github_issues_processed"] = result.get("github_issues_processed", 0) + 1
                    if validation_result.is_valid:
                        _notify_github_validation(
                            record.github_issue_id,
                            validation_result,
                            logger,
                        )

                # Sleep between Ollama validations to prevent CPU/GPU overload
                if record.provider and record.provider.startswith("ollama"):
                    sleep_seconds = result["ollama_sleep"]
                    if sleep_seconds > 0:
                        logger.log_progress(
                            f"Ollama cooldown: sleeping {sleep_seconds}s"
                        )
                        time.sleep(sleep_seconds)
            else:
                result["warnings"].append(
                    f"Failed to validate {record.id}: {str(last_error)}"
                )
                logger.warning(
                    "VALIDATION_FAILED",
                    record_id=record.id[:12] if record.id else None,
                    error=str(last_error)[:100] if last_error else "unknown",
                )

            # Log progress periodically
            if (idx + 1) % 10 == 0:
                logger.log_progress(
                    "Processing contributions",
                    current=idx + 1,
                    total=len(pending_records),
                    validated=result["contributions_validated"],
                )

        # Save updated records back to MockupStorage
        if updated_records:
            saved_count = storage.save_batch(updated_records)
            result["contributions_saved"] = saved_count

        # Mark task as completed
        result["status"] = "success"
        redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)

        logger.log_completed(
            status="success",
            validated=result["contributions_validated"],
            approved=result["contributions_approved"],
            flagged=result["contributions_flagged"],
            providers=",".join(result["providers_tried"]),
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


def _build_body(constat_factuel: str, idees_ameliorations: str) -> str:
    """
    Build contribution body from Framaforms fields.

    Args:
        constat_factuel: Factual observation field
        idees_ameliorations: Improvement ideas field

    Returns:
        Formatted body text
    """
    parts = []
    if constat_factuel:
        parts.append(f"**Constat factuel:**\n{constat_factuel}")
    if idees_ameliorations:
        parts.append(f"**Idées d'améliorations:**\n{idees_ameliorations}")
    return "\n\n".join(parts) if parts else ""


def _notify_github_validation(issue_id: int, validation_result, logger) -> bool:
    """
    Notify N8N to add 'conforme charte' label to a validated GitHub issue.

    Args:
        issue_id: GitHub issue number
        validation_result: Forseti validation result
        logger: Task logger instance

    Returns:
        True if notification was successful
    """
    import requests

    N8N_CHARTER_VALID_WEBHOOK = "https://vaettir.locki.io/webhook/forseti/charter-valid"

    try:
        response = requests.post(
            N8N_CHARTER_VALID_WEBHOOK,
            json={
                "issueNumber": issue_id,
                "is_valid": validation_result.is_valid,
                "category": validation_result.category,
                "confidence": validation_result.confidence,
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.ok:
            logger.info(
                "GITHUB_LABEL_ADDED",
                issue_id=issue_id,
                category=validation_result.category,
            )
            return True
        else:
            logger.warning(
                "GITHUB_LABEL_FAILED",
                issue_id=issue_id,
                status_code=response.status_code,
            )
            return False

    except requests.RequestException as e:
        logger.warning(
            "GITHUB_WEBHOOK_ERROR",
            issue_id=issue_id,
            error=str(e)[:50],
        )
        return False
