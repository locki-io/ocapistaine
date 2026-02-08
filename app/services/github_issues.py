"""
GitHub Issues Service

Fetches and processes issues from audierne2026/participons repository
via N8N webhook. Includes French date parsing from issue titles.
"""

import re
import time
from datetime import datetime, date
from typing import Optional

import requests

from app.services.logging import ServiceLogger

logger = ServiceLogger("github_issues")

# N8N Webhook URL for fetching issues
N8N_ISSUES_WEBHOOK = "https://vaettir.locki.io/webhook/participons/issues"

# French month names to month numbers
FRENCH_MONTHS = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}

# French date pattern: "Samedi, janvier 24, 2026" or "janvier 24, 2026"
FRENCH_DATE_PATTERN = re.compile(
    r"(?:\w+,\s*)?(\w+)\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE
)


def parse_french_date(title: str) -> Optional[date]:
    """
    Parse French date from issue title.

    Handles formats like:
    - "Samedi, janvier 24, 2026"
    - "janvier 24, 2026"
    - "24 janvier 2026"

    Args:
        title: Issue title containing French date

    Returns:
        Parsed date or None if not found
    """
    if not title:
        return None

    # Try pattern: "Samedi, janvier 24, 2026"
    match = FRENCH_DATE_PATTERN.search(title)
    if match:
        month_str, day_str, year_str = match.groups()
        month_lower = month_str.lower()

        if month_lower in FRENCH_MONTHS:
            try:
                return date(
                    year=int(year_str),
                    month=FRENCH_MONTHS[month_lower],
                    day=int(day_str)
                )
            except ValueError:
                pass

    # Try alternative pattern: "24 janvier 2026"
    alt_pattern = re.compile(
        r"(\d{1,2})\s+(\w+)\s+(\d{4})",
        re.IGNORECASE
    )
    match = alt_pattern.search(title)
    if match:
        day_str, month_str, year_str = match.groups()
        month_lower = month_str.lower()

        if month_lower in FRENCH_MONTHS:
            try:
                return date(
                    year=int(year_str),
                    month=FRENCH_MONTHS[month_lower],
                    day=int(day_str)
                )
            except ValueError:
                pass

    return None


def fetch_issues(
    state: str = "open",
    labels: str = "",
    per_page: int = 100
) -> dict:
    """
    Fetch issues from N8N workflow webhook.

    Args:
        state: Issue state ("open", "closed", "all")
        labels: Comma-separated labels to filter by
        per_page: Number of issues to fetch

    Returns:
        dict with keys: success, count, issues, error
    """
    start_time = time.time()
    try:
        payload = {"state": state, "per_page": per_page}
        if labels:
            payload["labels"] = labels

        response = requests.post(
            N8N_ISSUES_WEBHOOK,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

        latency_ms = (time.time() - start_time) * 1000
        logger.debug(
            "ISSUES_FETCHED",
            count=result.get("count", 0),
            state=state,
            labels=labels or "all",
            latency_ms=f"{latency_ms:.0f}",
        )

        return result
    except requests.RequestException as e:
        logger.warning(
            "ISSUES_FETCH_FAILED",
            error=str(e)[:100],
            state=state,
        )
        return {"success": False, "error": str(e), "count": 0, "issues": []}


def get_issues_with_dates(
    state: str = "all",
    per_page: int = 100
) -> list[dict]:
    """
    Fetch issues and enrich with parsed dates from titles.

    Args:
        state: Issue state filter
        per_page: Max issues to fetch

    Returns:
        List of issue dicts with added 'parsed_date' field
    """
    result = fetch_issues(state=state, per_page=per_page)

    if not result.get("success"):
        return []

    issues = result.get("issues", [])

    for issue in issues:
        title = issue.get("title", "")
        issue["parsed_date"] = parse_french_date(title)

    return issues


def get_issues_counts(
    after_date: Optional[str] = None,
    pending_only: bool = False
) -> dict:
    """
    Get counts of GitHub issues with optional date filtering.

    Args:
        after_date: Only count issues after this date (ISO format: YYYY-MM-DD)
        pending_only: If True, only count issues without 'conforme charte' label

    Returns:
        dict with keys: total, pending, validated, date_range
    """
    # Fetch all issues (open and closed)
    issues = get_issues_with_dates(state="all", per_page=200)

    # Convert after_date string to date object
    filter_date = None
    if after_date:
        try:
            filter_date = date.fromisoformat(after_date)
        except ValueError:
            logger.warning("INVALID_DATE_FORMAT", after_date=after_date)

    # Filter by date if specified
    if filter_date:
        issues = [
            issue for issue in issues
            if issue.get("parsed_date") and issue["parsed_date"] >= filter_date
        ]

    # Calculate counts
    total = len(issues)
    validated = sum(1 for i in issues if i.get("has_conforme_charte", False))
    pending = total - validated

    # Get date range
    dates = [i["parsed_date"] for i in issues if i.get("parsed_date")]
    date_range = {}
    if dates:
        date_range = {
            "min": min(dates).isoformat(),
            "max": max(dates).isoformat(),
        }

    return {
        "total": total,
        "pending": pending,
        "validated": validated,
        "date_range": date_range,
        "source": "GitHub Issues",
    }


def get_issues_for_validation(
    after_date: Optional[str] = None,
    limit: int = 100
) -> list[dict]:
    """
    Get GitHub issues ready for validation (without 'conforme charte' label).

    Args:
        after_date: Only include issues after this date (ISO format)
        limit: Maximum number of issues to return

    Returns:
        List of issue dicts suitable for Forseti validation
    """
    issues = get_issues_with_dates(state="all", per_page=200)

    # Convert after_date string to date object
    filter_date = None
    if after_date:
        try:
            filter_date = date.fromisoformat(after_date)
        except ValueError:
            pass

    # Filter: pending validation + date filter
    pending_issues = []
    for issue in issues:
        # Skip already validated
        if issue.get("has_conforme_charte", False):
            continue

        # Apply date filter
        if filter_date:
            parsed = issue.get("parsed_date")
            if not parsed or parsed < filter_date:
                continue

        pending_issues.append(issue)

        if len(pending_issues) >= limit:
            break

    return pending_issues
