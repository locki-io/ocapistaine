# app/services/tasks/task_audierne_docs.py
"""
Audierne Docs Processing Task

Processes audierne2026 markdown documents one by one to generate
themed contributions with violations for Forseti testing.

Runs every 2 hours during development to:
1. Check progress file for already-processed docs
2. Acquire Ollama lock (if using local LLM)
3. Process the next unprocessed document
4. Generate themed contributions (with violations)
5. Create Opik dataset for the document
6. Update progress file
7. Release Ollama lock

Failover: If Ollama is unavailable, automatically falls back to gemini.

Progress tracked in: docs/docs/audierne2026/PROCESSING_PROGRESS.md
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.services.tasks import _task_boilerplate, TaskError, REDIS_SUCCESS_TTL
from app.services.logging import TaskLogger
from app.services.scheduler.utils import get_scheduler_redis, sched_key

# Paths
AUDIERNE_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "docs" / "audierne2026"
PROGRESS_FILE = AUDIERNE_DOCS_DIR / "PROCESSING_PROGRESS.md"

# Task configuration
DEFAULT_PROVIDER = "ollama"
FALLBACK_PROVIDER = "gemini"  # Used when Ollama is unavailable
CONTRIBUTIONS_PER_THEME = 2
INCLUDE_VIOLATIONS = True
OLLAMA_LOCK_TTL = 600  # 10 minutes for document processing

_logger = TaskLogger("task_audierne_docs")


def _acquire_ollama_lock(task_id: str) -> bool:
    """Acquire global Ollama lock to prevent concurrent usage."""
    try:
        redis = get_scheduler_redis()
        lock_key = sched_key("lock:ollama:global")
        acquired = redis.set(lock_key, task_id, ex=OLLAMA_LOCK_TTL, nx=True)
        if acquired:
            _logger.debug("OLLAMA_LOCK_ACQUIRED", task_id=task_id)
        return bool(acquired)
    except Exception as e:
        _logger.warning("OLLAMA_LOCK_ERROR", error=str(e))
        return False


def _release_ollama_lock(task_id: str) -> None:
    """Release Ollama lock if we hold it."""
    try:
        redis = get_scheduler_redis()
        lock_key = sched_key("lock:ollama:global")
        current = redis.get(lock_key)
        if current:
            # Handle both bytes and str returns from Redis
            current_str = current.decode() if isinstance(current, bytes) else current
            if current_str == task_id:
                redis.delete(lock_key)
                _logger.debug("OLLAMA_LOCK_RELEASED", task_id=task_id)
    except Exception as e:
        _logger.warning("OLLAMA_LOCK_RELEASE_ERROR", error=str(e))


def _get_all_docs() -> list[dict]:
    """
    Get all processable markdown documents in audierne2026 folder.

    Returns:
        List of dicts with path, filename, title, and size.
    """
    docs = []

    if not AUDIERNE_DOCS_DIR.exists():
        return docs

    for md_file in sorted(AUDIERNE_DOCS_DIR.glob("*.md")):
        # Skip progress file and empty files
        if md_file.name == "PROCESSING_PROGRESS.md":
            continue

        size = md_file.stat().st_size
        if size < 100:  # Skip nearly empty files
            continue

        # Extract title from filename
        title = md_file.stem.replace("-", " ").replace("_", " ").title()

        docs.append({
            "path": str(md_file),
            "filename": md_file.name,
            "title": title,
            "size": size,
        })

    return docs


def _read_progress() -> dict:
    """
    Read progress from the tracking file.

    Returns:
        Dict with processed docs and metadata.
    """
    if not PROGRESS_FILE.exists():
        return {"processed": [], "last_updated": None}

    content = PROGRESS_FILE.read_text()

    # Parse markdown table to extract processed filenames
    processed = []
    for line in content.split("\n"):
        if line.startswith("| ") and "✅" in line:
            # Extract filename from table row
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                filename = parts[1].strip()
                if filename and filename != "File":
                    processed.append(filename)

    return {"processed": processed, "last_updated": datetime.now().isoformat()}


def _write_progress(processed_docs: list[dict], all_docs: list[dict]):
    """
    Write progress to the tracking file.

    Args:
        processed_docs: List of processed doc info dicts.
        all_docs: List of all available docs.
    """
    lines = [
        "# Audierne2026 Document Processing Progress",
        "",
        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Total documents: {len(all_docs)}",
        f"Processed: {len(processed_docs)}",
        f"Remaining: {len(all_docs) - len(processed_docs)}",
        "",
        "## Progress",
        "",
        "| File | Status | Processed At | Themes | Contributions | Dataset |",
        "|------|--------|--------------|--------|---------------|---------|",
    ]

    # Add processed docs
    processed_filenames = {d["filename"] for d in processed_docs}

    for doc in all_docs:
        filename = doc["filename"]
        if filename in processed_filenames:
            # Find the processed info
            info = next((d for d in processed_docs if d["filename"] == filename), {})
            processed_at = info.get("processed_at", "Unknown")
            themes = info.get("themes", 0)
            contributions = info.get("contributions", 0)
            dataset = info.get("dataset", "N/A")
            lines.append(f"| {filename} | ✅ Done | {processed_at} | {themes} | {contributions} | {dataset} |")
        else:
            lines.append(f"| {filename} | ⏳ Pending | - | - | - | - |")

    lines.extend([
        "",
        "## Processing Log",
        "",
    ])

    # Add processing log entries
    for doc in processed_docs:
        log_entry = doc.get("log_entry", "")
        if log_entry:
            lines.append(f"- {log_entry}")

    PROGRESS_FILE.write_text("\n".join(lines))


def _get_next_doc(all_docs: list[dict], processed_filenames: set[str]) -> Optional[dict]:
    """
    Get the next unprocessed document.

    Args:
        all_docs: All available documents.
        processed_filenames: Set of already processed filenames.

    Returns:
        Next doc to process or None if all done.
    """
    for doc in all_docs:
        if doc["filename"] not in processed_filenames:
            return doc
    return None


def task_audierne_docs(
    date_string: str = None,
    provider: str = DEFAULT_PROVIDER,
    model: str = None,
    contributions_per_theme: int = CONTRIBUTIONS_PER_THEME,
    include_violations: bool = INCLUDE_VIOLATIONS,
    force_doc: str = None,
    enable_failover: bool = True,
) -> dict:
    """
    Process one audierne2026 document and create dataset.

    Args:
        date_string: Date string for task identification.
        provider: LLM provider to use.
        model: Optional model override.
        contributions_per_theme: Contributions per extracted theme.
        include_violations: Whether to include violation examples.
        force_doc: Force processing a specific document filename.
        enable_failover: If True, fall back to gemini if Ollama unavailable.

    Returns:
        Task result dict.
    """
    # Use unique key per doc processing (skip_success_check for recurring)
    redis_conn, lock_key, success_key, result, task_id, logger = _task_boilerplate(
        "task_audierne_docs", date_string, skip_success_check=True
    )

    if result["status"] == "skipped":
        return result

    ollama_locked = False
    effective_provider = provider

    try:
        from app.mockup.field_input import process_field_input_sync
        from app.mockup.dataset import get_dataset_manager

        # Get all docs and progress
        all_docs = _get_all_docs()
        progress = _read_progress()
        processed_filenames = set(progress["processed"])

        logger.info(
            "AUDIERNE_DOCS_STATUS",
            total=len(all_docs),
            processed=len(processed_filenames),
            remaining=len(all_docs) - len(processed_filenames),
        )

        if not all_docs:
            result["status"] = "skipped"
            result["reason"] = "no_docs_found"
            logger.log_skipped(reason="no_docs_found")
            return result

        # Get next doc to process
        if force_doc:
            doc = next((d for d in all_docs if d["filename"] == force_doc), None)
            if not doc:
                result["status"] = "failed"
                result["errors"].append(f"Document not found: {force_doc}")
                return result
        else:
            doc = _get_next_doc(all_docs, processed_filenames)

        if not doc:
            result["status"] = "success"
            result["reason"] = "all_docs_processed"
            logger.info("ALL_DOCS_PROCESSED", total=len(all_docs))
            redis_conn.set(success_key, "all_complete", ex=REDIS_SUCCESS_TTL)
            return result

        # Handle Ollama lock and failover
        if provider == "ollama":
            if _acquire_ollama_lock(task_id):
                ollama_locked = True
                logger.info("USING_OLLAMA", task_id=task_id)
            elif enable_failover:
                effective_provider = FALLBACK_PROVIDER
                logger.info("OLLAMA_BUSY_FAILOVER", fallback=FALLBACK_PROVIDER)
                result["warnings"].append(f"Ollama busy, using {FALLBACK_PROVIDER}")
            else:
                result["status"] = "skipped"
                result["reason"] = "ollama_locked"
                result["warnings"].append("Ollama is locked by another task")
                logger.log_skipped(reason="ollama_locked")
                return result

        # Read document content
        doc_path = Path(doc["path"])
        content = doc_path.read_text(encoding="utf-8")

        logger.info(
            "PROCESSING_DOC",
            filename=doc["filename"],
            size=len(content),
            provider=effective_provider,
        )

        # Process with field input
        field_result = process_field_input_sync(
            input_text=content,
            source_file=doc["path"],
            source_title=doc["title"],
            provider=effective_provider,
            model=model,
            contributions_per_theme=contributions_per_theme,
            include_violations=include_violations,
        )

        logger.info(
            "DOC_PROCESSED",
            filename=doc["filename"],
            themes=field_result.themes_extracted,
            contributions=field_result.contributions_generated,
        )

        # Create Opik dataset for this document
        dataset_name = f"audierne-{doc['filename'].replace('.md', '')}-{date_string}"

        try:
            manager = get_dataset_manager()
            manager.create_charter_dataset(
                name=dataset_name,
                description=f"Generated from {doc['filename']} on {datetime.now().isoformat()}",
            )

            # Add contributions to dataset from Redis
            count = manager.add_from_redis(
                dataset_name=dataset_name,
                date_str=datetime.now().strftime("%Y-%m-%d"),
            )

            logger.info("DATASET_CREATED", name=dataset_name, items=count)
        except Exception as e:
            logger.warning("DATASET_CREATION_FAILED", error=str(e))
            dataset_name = "N/A (error)"

        # Update progress
        processed_doc_info = {
            "filename": doc["filename"],
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "themes": field_result.themes_extracted,
            "contributions": field_result.contributions_generated,
            "dataset": dataset_name,
            "log_entry": f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Processed {doc['filename']}: {field_result.themes_extracted} themes, {field_result.contributions_generated} contributions",
        }

        # Read existing processed docs and add new one
        existing_progress = _read_progress()
        processed_docs = []

        # Re-read processed info from file (reconstruct from progress file)
        for filename in existing_progress["processed"]:
            processed_docs.append({"filename": filename})

        processed_docs.append(processed_doc_info)

        _write_progress(processed_docs, all_docs)

        # Set result
        result["status"] = "success"
        result["doc_processed"] = doc["filename"]
        result["themes_extracted"] = field_result.themes_extracted
        result["contributions_generated"] = field_result.contributions_generated
        result["dataset_name"] = dataset_name
        result["remaining_docs"] = len(all_docs) - len(processed_filenames) - 1
        result["provider_used"] = effective_provider

        logger.log_completed(
            status="success",
            doc=doc["filename"],
            themes=field_result.themes_extracted,
            contributions=field_result.contributions_generated,
        )

        return result

    except Exception as e:
        result["status"] = "failed"
        result["errors"].append(str(e))
        logger.log_failed(error=str(e))
        raise TaskError("failed", str(e))
    finally:
        # Release Ollama lock if we hold it
        if ollama_locked:
            _release_ollama_lock(task_id)
        redis_conn.delete(lock_key)
