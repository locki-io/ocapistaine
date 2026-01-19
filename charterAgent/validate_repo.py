#!/usr/bin/env python3
import sys
import re
import requests
from charter_agent import GeminiClient, OpikTracer, ValidationResult

def extract_repo(url):
    """
    Extract owner/repo from a GitHub URL.

    Args:
        url: GitHub issue or repo URL.

    Returns:
        "owner/repo" string or None if not matched.
    """
    match = re.search(r'github\.com/([^/]+/[^/?]+)', url)
    return match.group(1) if match else None

def main():
    """
    CLI entrypoint for batch validation.

    Args:
        argv[1]: GitHub URL.
    """
    if len(sys.argv) < 2:
        print("Usage: python validate_repo.py <github-repo-url>")
        sys.exit(1)
    
    repo = extract_repo(sys.argv[1])
    if not repo:
        print("Invalid GitHub URL")
        sys.exit(1)
    
    print(f"Validating issues from {repo}...\n")
    
    query = f"repo:{repo} is:issue state:open type:Task"
    response = requests.get(f"https://api.github.com/search/issues?q={query}&per_page=100")
    data = response.json()
    issues = data.get("items", [])
    
    print(f"Found {len(issues)} Task issues\n")
    
    gemini = GeminiClient()
    opik = OpikTracer()
    
    valid = invalid = corrected = 0
    batch = []
    batch_meta = {}
    batch_size = 5
    processed = 0

    def flush_batch():
        nonlocal valid, invalid, corrected, processed, batch, batch_meta
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

            print(f"[{processed}/{len(issues)}] #{issue.get('number')}: {issue.get('title', '')[:60]}...")
            print(f"  Category: {original_category or 'none'}")
            print(f"  Valid: {result.is_valid} | Predicted: {result.category} | Confidence: {result.confidence:.2f}")
            if result.reasoning:
                one_line = " ".join(result.reasoning.split())
                print(f"  Reason: {one_line[:180]}")

            if result.is_valid:
                valid += 1
            else:
                invalid += 1
                print(f"  VIOLATIONS: {', '.join(result.violations)}")

            if result.original_category and result.original_category != result.category:
                corrected += 1
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

    for issue in issues:
        if "pull_request" in issue:
            continue
        
        body = issue["body"] or ""
        category = None
        
        if body.startswith("Category:") or "Category:" in body[:100]:
            lines = body.split("\n")
            for line in lines[:3]:
                if "Category:" in line:
                    category = line.split("Category:")[-1].strip().lower()
                    break
        if not category:
            m = re.search(r"\[([^\]]+)\]", issue["title"])
            if m:
                category = m.group(1).strip().lower()
        
        item = {
            "id": str(issue["number"]),
            "title": issue["title"],
            "body": body,
            "category": category,
        }
        batch.append(item)
        batch_meta[item["id"]] = {"issue": issue, "category": category}
        if len(batch) >= batch_size:
            flush_batch()

    flush_batch()
    
    print(f"\n{'='*50}")
    print(f"Valid: {valid} | Invalid: {invalid} | Corrected: {corrected}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()

