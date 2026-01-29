# app/prompts/opik_sync.py
"""
Opik Prompt Synchronization

Sync local prompts to Opik Prompt Library for versioning and optimization.

Usage:
    # Sync all prompts
    python -m app.prompts.opik_sync

    # Or programmatically
    from app.prompts.opik_sync import sync_all_prompts
    results = sync_all_prompts()
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

from app.prompts.local import LOCAL_PROMPTS
from app.services import AgentLogger

_logger = AgentLogger("opik_sync")


def get_opik_client():
    """Get Opik client, return None if not available."""
    try:
        import opik
        return opik.Opik()
    except ImportError:
        _logger.error("OPIK_NOT_INSTALLED", message="pip install opik")
        return None
    except Exception as e:
        _logger.error("OPIK_INIT_FAILED", error=str(e))
        return None


def sync_prompt_to_opik(
    name: str,
    template: str,
    metadata: Optional[Dict[str, Any]] = None,
    client=None,
) -> Dict[str, Any]:
    """
    Sync a single prompt to Opik library.

    Args:
        name: Prompt name (e.g., "forseti.charter_validation")
        template: Prompt template string
        metadata: Optional metadata dict
        client: Optional Opik client (will create if not provided)

    Returns:
        Dict with sync result: {"success": bool, "name": str, "commit": str|None}
    """
    if client is None:
        client = get_opik_client()

    if client is None:
        return {"success": False, "name": name, "error": "Opik not available"}

    try:
        # Create or update prompt
        prompt = client.create_prompt(
            name=name,
            prompt=template,
            metadata=metadata or {},
        )

        commit_id = getattr(prompt, "commit", None)

        _logger.info(
            "PROMPT_SYNCED",
            name=name,
            commit=commit_id,
        )

        return {
            "success": True,
            "name": name,
            "commit": commit_id,
        }

    except Exception as e:
        _logger.error("PROMPT_SYNC_FAILED", name=name, error=str(e))
        return {
            "success": False,
            "name": name,
            "error": str(e),
        }


def sync_all_prompts(
    filter_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sync all local prompts to Opik.

    Args:
        filter_prefix: Optional prefix to filter prompts (e.g., "forseti.")

    Returns:
        Dict with results: {"synced": [...], "failed": [...], "total": int}
    """
    client = get_opik_client()
    if client is None:
        return {
            "synced": [],
            "failed": list(LOCAL_PROMPTS.keys()),
            "total": len(LOCAL_PROMPTS),
            "error": "Opik not available",
        }

    synced = []
    failed = []

    for name, prompt_data in LOCAL_PROMPTS.items():
        # Filter by prefix if specified
        if filter_prefix and not name.startswith(filter_prefix):
            continue

        # Build metadata
        metadata = {
            "type": prompt_data.get("type", "user"),
            "variables": prompt_data.get("variables", []),
            "description": prompt_data.get("description", ""),
            "synced_at": datetime.now().isoformat(),
            "source": "ocapistaine",
        }

        if "language" in prompt_data:
            metadata["language"] = prompt_data["language"]

        result = sync_prompt_to_opik(
            name=name,
            template=prompt_data["template"],
            metadata=metadata,
            client=client,
        )

        if result["success"]:
            synced.append(result)
        else:
            failed.append(result)

    total = len(synced) + len(failed)
    _logger.info(
        "SYNC_COMPLETE",
        synced=len(synced),
        failed=len(failed),
        total=total,
    )

    return {
        "synced": synced,
        "failed": failed,
        "total": total,
    }


def get_prompt_versions(name: str) -> List[Dict[str, Any]]:
    """
    Get version history for a prompt from Opik.

    Args:
        name: Prompt name

    Returns:
        List of version dicts with commit, created_at
    """
    client = get_opik_client()
    if client is None:
        return []

    try:
        history = client.get_prompt_history(name=name)
        return [
            {
                "commit": getattr(v, "commit", None),
                "created_at": getattr(v, "created_at", None),
            }
            for v in history
        ]
    except Exception as e:
        _logger.error("GET_VERSIONS_FAILED", name=name, error=str(e))
        return []


def compare_local_vs_opik() -> Dict[str, Any]:
    """
    Compare local prompts with Opik library.

    Returns:
        Dict with: {"in_sync": [...], "local_only": [...], "opik_only": [...]}
    """
    client = get_opik_client()
    if client is None:
        return {
            "in_sync": [],
            "local_only": list(LOCAL_PROMPTS.keys()),
            "opik_only": [],
            "error": "Opik not available",
        }

    local_names = set(LOCAL_PROMPTS.keys())
    opik_names = set()

    # Try to list prompts from Opik
    try:
        # Get prompts we know about
        for name in local_names:
            try:
                client.get_prompt(name=name)
                opik_names.add(name)
            except Exception:
                pass
    except Exception as e:
        _logger.error("COMPARE_FAILED", error=str(e))

    in_sync = local_names & opik_names
    local_only = local_names - opik_names
    opik_only = opik_names - local_names

    return {
        "in_sync": list(in_sync),
        "local_only": list(local_only),
        "opik_only": list(opik_only),
    }


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI entry point for syncing prompts."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync prompts to Opik")
    parser.add_argument(
        "--prefix",
        type=str,
        default=None,
        help="Filter prompts by prefix (e.g., 'forseti.')",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare local vs Opik without syncing",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List local prompts",
    )

    args = parser.parse_args()

    if args.list:
        print("\nLocal Prompts:")
        print("-" * 50)
        for name, data in LOCAL_PROMPTS.items():
            print(f"  {name}")
            print(f"    Type: {data.get('type', 'user')}")
            print(f"    Variables: {data.get('variables', [])}")
            print(f"    Description: {data.get('description', '')[:60]}...")
            print()
        return

    if args.compare:
        print("\nComparing local vs Opik...")
        result = compare_local_vs_opik()
        print(f"\nIn sync: {len(result['in_sync'])}")
        for name in result["in_sync"]:
            print(f"  ✅ {name}")
        print(f"\nLocal only: {len(result['local_only'])}")
        for name in result["local_only"]:
            print(f"  📁 {name}")
        print(f"\nOpik only: {len(result['opik_only'])}")
        for name in result["opik_only"]:
            print(f"  ☁️  {name}")
        return

    print("\nSyncing prompts to Opik...")
    if args.prefix:
        print(f"Filtering by prefix: {args.prefix}")

    result = sync_all_prompts(filter_prefix=args.prefix)

    print(f"\nResults:")
    print(f"  Synced: {len(result['synced'])}")
    for item in result["synced"]:
        print(f"    ✅ {item['name']} (commit: {item.get('commit', 'N/A')})")

    print(f"  Failed: {len(result['failed'])}")
    for item in result["failed"]:
        print(f"    ❌ {item['name']}: {item.get('error', 'Unknown error')}")

    print(f"\nTotal: {result['total']}")


if __name__ == "__main__":
    main()
