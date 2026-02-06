#!/usr/bin/env python
"""
Re-validate contributions with errors using OpenAI failover.

This script finds all contributions in Redis that have validation errors
(like Ollama 404s) and re-validates them using OpenAI.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def revalidate_errors():
    from app.mockup.storage import get_storage
    from app.agents.forseti import ForsetiAgent
    from app.providers import get_provider

    storage = get_storage()

    # Get all records
    records = storage.get_latest_validations(limit=500)

    # Find error records
    error_patterns = ["error", "404", "failed", "timeout", "retries", "rate limit", "classification error"]
    error_records = [
        r
        for r in records
        if any(p in (r.reasoning or "").lower() for p in error_patterns)
    ]

    print(f"Found {len(error_records)} records with errors", flush=True)
    print(f"Will re-validate using OpenAI (gpt-4o-mini)", flush=True)
    print(flush=True)

    if not error_records:
        print("No error records to re-validate.", flush=True)
        return 0, 0

    # Use OpenAI - most reliable for batch operations
    # Failover chain: openai → claude → mistral → gemini
    provider = get_provider("openai")
    agent = ForsetiAgent(provider=provider)

    revalidated = 0
    failed = 0

    for i, record in enumerate(error_records):
        try:
            print(
                f"[{i+1}/{len(error_records)}] Re-validating {record.id[:12]}...",
                end=" ",
                flush=True,
            )

            # Re-validate
            result = await agent.validate(
                title=record.title,
                body=record.body,
                category=record.category,
            )

            # Update record
            record.is_valid = result.is_valid
            record.violations = result.violations
            record.encouraged_aspects = result.encouraged_aspects
            record.confidence = result.confidence
            record.reasoning = result.reasoning
            record.suggested_category = result.category
            record.provider = f"openai:{provider.model}"
            record.timestamp = datetime.now().isoformat()

            # Save updated record
            storage.save_validation(record)

            status = "VALID" if result.is_valid else "INVALID"
            print(f"{status} (conf={result.confidence:.2f})", flush=True)
            revalidated += 1

        except Exception as e:
            print(f"FAILED: {str(e)[:80]}", flush=True)
            failed += 1

    print(flush=True)
    print("=== SUMMARY ===", flush=True)
    print(f"Revalidated: {revalidated}", flush=True)
    print(f"Failed: {failed}", flush=True)

    return revalidated, failed


if __name__ == "__main__":
    revalidated, failed = asyncio.run(revalidate_errors())
    sys.exit(0 if failed == 0 else 1)
