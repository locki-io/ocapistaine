"""
Daily Contributions Analysis Task

Analyzes and validates pending citizen contributions from various sources:
- Mockup storage (Redis db=5) - ValidationRecords awaiting Forseti analysis
- GitHub issues (audierne2026/participons) - Future integration
- Facebook/Email submissions (via Vaettir) - Future integration

Uses Forseti agent for validation against contribution charter.
Results are stored back in MockupStorage for Opik dataset export.
"""

import asyncio
from datetime import datetime

from app.services.tasks import _task_boilerplate, TaskError, REDIS_SUCCESS_TTL


def task_contributions_analysis(
    date_string: str = None,
    provider: str = None,
    enable_failover: bool = True,
    limit: int = 100,
    ollama_model: str = None,
) -> dict:
    """
    Analyze and validate pending contributions from MockupStorage.

    Workflow:
    1. Fetch latest validations from MockupStorage (Redis db=5)
    2. Filter for records needing validation (confidence == 0)
    3. Run Forseti validation on each contribution
    4. Update records in MockupStorage with results
    5. Mark task completed in scheduler db (Redis db=6)

    Args:
        date_string: Date in YYYYMMDD format. Defaults to today.
        provider: LLM provider name ("gemini", "claude", "mistral", "ollama").
        enable_failover: If True, try fallback providers on rate limit errors.
        limit: Maximum number of contributions to process (default 100).
        ollama_model: Specific Ollama model (e.g., "deepseek-r1:7b", "qwen3:4b").

    Returns:
        dict: Result with status, counts, and any errors

    Raises:
        TaskError: If critical failure occurs during processing
    """
    redis_conn, lock_key, success_key, result, task_id = _task_boilerplate(
        "task_contributions_analysis", date_string
    )

    # Store provider config in result
    result["provider"] = provider
    result["enable_failover"] = enable_failover
    result["limit"] = limit
    result["ollama_model"] = ollama_model

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

        # Fetch contributions from MockupStorage (Redis db=5)
        from app.mockup.storage import get_storage
        from datetime import date, timedelta

        storage = get_storage()

        # Try latest validations first
        records = storage.get_latest_validations(limit=100)

        # If latest is empty, check recent date indexes (last 7 days)
        if not records:
            print("task_contributions_analysis: latest empty, checking date indexes")
            all_records = []
            for days_ago in range(7):
                check_date = date.today() - timedelta(days=days_ago)
                date_records = storage.get_validations_by_date(check_date.isoformat())
                all_records.extend(date_records)
            records = all_records[:100]  # Limit to 100

        result["contributions_fetched"] = len(records)

        if not records:
            result["status"] = "success"
            result["reason"] = "no_contributions_to_process"
            redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)
            print("task_contributions_analysis: no contributions to process")
            return result

        # Filter for records needing validation (confidence == 0 means not yet validated)
        pending_records = [r for r in records if r.confidence == 0.0][:limit]

        if not pending_records:
            result["status"] = "success"
            result["reason"] = "all_contributions_already_validated"
            result["contributions_skipped"] = len(records)
            redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)
            print(
                f"task_contributions_analysis: all {len(records)} contributions already validated"
            )
            return result

        # Initialize Forseti agent with provider selection and failover
        from app.agents.forseti import ForsetiAgent

        # Failover provider order
        PROVIDER_FAILOVER_ORDER = ["gemini", "claude", "mistral", "ollama"]

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
                # No provider specified and no failover, use default
                providers.append("gemini")
            return providers

        providers_to_try = get_providers_to_try()
        result["providers_tried"] = []

        # Process each pending contribution
        updated_records = []
        for record in pending_records:
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
                        print(
                            f"task_contributions_analysis: {try_provider} rate limited, "
                            f"trying next provider"
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

                if validation_result.is_valid:
                    result["contributions_approved"] += 1
                else:
                    result["contributions_flagged"] += 1

                result["contributions_validated"] += 1
            else:
                result["warnings"].append(
                    f"Failed to validate {record.id}: {str(last_error)}"
                )
                print(
                    f"task_contributions_analysis: error validating {record.id}: "
                    f"{last_error}"
                )

        # Save updated records back to MockupStorage
        if updated_records:
            saved_count = storage.save_batch(updated_records)
            result["contributions_saved"] = saved_count

        # Mark task as completed
        result["status"] = "success"
        redis_conn.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)

        print(
            f"task_contributions_analysis completed: "
            f"{result['contributions_validated']} validated, "
            f"{result['contributions_approved']} approved, "
            f"{result['contributions_flagged']} flagged"
        )
        return result

    except Exception as e:
        result["status"] = "failed"
        result["errors"].append(str(e))
        print(f"task_contributions_analysis failed: {e}")
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
