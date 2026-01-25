#!/usr/bin/env python3
"""
GitHub Repository Validator

Validates all Task issues in a GitHub repository using Forseti 461 agent.

Usage:
    python validate_repo.py <github-repo-url>
    python validate_repo.py https://github.com/audierne2026/participons

Supports both the new ForsetiAgent (preferred) and legacy GeminiClient.
"""

import sys
import re
import asyncio
import requests

# Try new agent first, fall back to legacy
try:
    from app.agents.forseti import ForsetiAgent, BatchItem
    from app.agents.tracing import get_tracer
    USE_NEW_AGENT = True
except ImportError:
    from charter_agent import GeminiClient, OpikTracer, ValidationResult
    USE_NEW_AGENT = False


def extract_repo(url: str) -> str | None:
    """
    Extract owner/repo from a GitHub URL.

    Args:
        url: GitHub issue or repo URL.

    Returns:
        "owner/repo" string or None if not matched.
    """
    match = re.search(r'github\.com/([^/]+/[^/?]+)', url)
    return match.group(1) if match else None


def extract_category(issue: dict) -> str | None:
    """
    Extract category from issue title or body.

    Args:
        issue: GitHub issue dict.

    Returns:
        Category string or None.
    """
    body = issue.get("body") or ""
    title = issue.get("title", "")

    # Try body first: "Category: xxx"
    if "Category:" in body[:100]:
        for line in body.split("\n")[:3]:
            if "Category:" in line:
                return line.split("Category:")[-1].strip().lower()

    # Try title: "[category]"
    match = re.search(r"\[([^\]]+)\]", title)
    if match:
        return match.group(1).strip().lower()

    return None


async def main_async():
    """Async main function for validation."""
    if len(sys.argv) < 2:
        print("Usage: python validate_repo.py <github-repo-url>")
        sys.exit(1)

    repo = extract_repo(sys.argv[1])
    if not repo:
        print("Invalid GitHub URL")
        sys.exit(1)

    print(f"Validating issues from {repo}...")
    print(f"Using: {'ForsetiAgent (new)' if USE_NEW_AGENT else 'GeminiClient (legacy)'}\n")

    # Fetch issues from GitHub
    query = f"repo:{repo} is:issue state:open type:Task"
    response = requests.get(
        f"https://api.github.com/search/issues?q={query}&per_page=100"
    )
    data = response.json()
    issues = data.get("items", [])

    print(f"Found {len(issues)} Task issues\n")

    if not issues:
        return

    # Filter out pull requests and prepare items
    task_issues = [i for i in issues if "pull_request" not in i]

    valid_count = 0
    invalid_count = 0
    corrected_count = 0

    if USE_NEW_AGENT:
        # Use new ForsetiAgent with batch processing
        agent = ForsetiAgent()
        tracer = get_tracer()

        # Process in batches of 5
        batch_size = 5
        for i in range(0, len(task_issues), batch_size):
            batch = task_issues[i:i + batch_size]
            batch_items = [
                BatchItem(
                    id=str(issue["number"]),
                    title=issue["title"],
                    body=issue.get("body") or "",
                    category=extract_category(issue),
                )
                for issue in batch
            ]

            results = await agent.validate_batch(batch_items)

            for result, issue in zip(results, batch):
                original_category = extract_category(issue)
                num = i + batch.index(issue) + 1

                print(f"[{num}/{len(task_issues)}] #{issue['number']}: {issue['title'][:60]}...")
                print(f"  Category: {original_category or 'none'}")
                print(f"  Valid: {result.is_valid} | Predicted: {result.category} | Confidence: {result.confidence:.2f}")

                if result.reasoning:
                    one_line = " ".join(result.reasoning.split())
                    print(f"  Reason: {one_line[:180]}")

                if result.is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1
                    print(f"  VIOLATIONS: {', '.join(result.violations)}")

                if original_category and original_category != result.category:
                    corrected_count += 1
                    print(f"  CORRECTED: {original_category} -> {result.category}")

                # Trace result
                tracer.trace_validation(
                    issue_data={
                        "title": issue["title"],
                        "body": issue.get("body"),
                        "category": original_category,
                    },
                    validation_result={
                        "is_valid": result.is_valid,
                        "violations": result.violations,
                        "encouraged_aspects": result.encouraged_aspects,
                        "confidence": result.confidence,
                        "reasoning": result.reasoning,
                    },
                    category_result={
                        "category": result.category,
                        "confidence": result.confidence,
                        "reasoning": result.reasoning,
                    },
                )

                print()

    else:
        # Legacy GeminiClient path
        gemini = GeminiClient()
        opik = OpikTracer()

        batch = []
        batch_meta = {}
        batch_size = 5
        processed = 0

        def flush_batch():
            nonlocal valid_count, invalid_count, corrected_count, processed, batch, batch_meta
            if not batch:
                return
            results = gemini.validate_and_classify_batch(batch)
            for r in results:
                processed += 1
                meta = batch_meta.get(r.get("id"), {})
                issue = meta.get("issue", {})
                original_category = meta.get("category")
                result = ValidationResult(
                    is_valid=r.get("is_valid", True),
                    category=r.get("category") or (original_category or "economie"),
                    original_category=original_category,
                    violations=r.get("violations", []),
                    encouraged_aspects=r.get("encouraged_aspects", []),
                    reasoning=r.get("reasoning", ""),
                    confidence=float(r.get("confidence", 0.5)),
                )

                print(f"[{processed}/{len(task_issues)}] #{issue.get('number')}: {issue.get('title', '')[:60]}...")
                print(f"  Category: {original_category or 'none'}")
                print(f"  Valid: {result.is_valid} | Predicted: {result.category} | Confidence: {result.confidence:.2f}")
                if result.reasoning:
                    one_line = " ".join(result.reasoning.split())
                    print(f"  Reason: {one_line[:180]}")

                if result.is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1
                    print(f"  VIOLATIONS: {', '.join(result.violations)}")

                if result.original_category and result.original_category != result.category:
                    corrected_count += 1
                    print(f"  CORRECTED: {result.original_category} -> {result.category}")

                opik.trace_validation(
                    {"title": issue.get("title"), "body": issue.get("body"), "category": original_category},
                    {
                        "is_valid": result.is_valid,
                        "violations": result.violations,
                        "encouraged_aspects": result.encouraged_aspects,
                        "confidence": result.confidence,
                        "reasoning": result.reasoning,
                    },
                    {
                        "category": result.category,
                        "confidence": result.confidence,
                        "reasoning": result.reasoning,
                    },
                )

                print()
            batch = []
            batch_meta = {}

        for issue in task_issues:
            category = extract_category(issue)
            item = {
                "id": str(issue["number"]),
                "title": issue["title"],
                "body": issue.get("body") or "",
                "category": category,
            }
            batch.append(item)
            batch_meta[item["id"]] = {"issue": issue, "category": category}
            if len(batch) >= batch_size:
                flush_batch()

        flush_batch()

    print(f"\n{'='*50}")
    print(f"Valid: {valid_count} | Invalid: {invalid_count} | Corrected: {corrected_count}")
    print(f"{'='*50}")


def main():
    """CLI entrypoint."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
