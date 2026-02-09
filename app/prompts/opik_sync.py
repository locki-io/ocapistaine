# app/prompts/opik_sync.py
"""
Opik Prompt Synchronization

Bidirectional sync between local prompts and Opik Prompt Library.
Push local prompts to Opik, or pull optimized composites back to update locals.

Usage:
    # Push all prompts
    python -m app.prompts.opik_sync --all

    # Pull optimized composite from Opik
    python -m app.prompts.opik_sync --pull forseti-persona-category

    # Pull all composites (dry run)
    python -m app.prompts.opik_sync --pull-all --dry-run

    # Pull + show performance data
    python -m app.prompts.opik_sync --pull forseti-persona-category --performance

    # Full round-trip: pull optimized → update locals → push all
    python -m app.prompts.opik_sync --pull-all && python -m app.prompts.opik_sync --all

    # Or programmatically
    from app.prompts.opik_sync import sync_all_prompts, pull_all_composites
    pull_result = pull_all_composites()
    sync_result = sync_all_prompts()
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.prompts.local import LOCAL_PROMPTS, JSON_PROMPTS
from app.prompts.local.json_loader import PROMPTS_DIR
from app.services import AgentLogger

_logger = AgentLogger("opik_sync")


# =============================================================================
# COMPOSITE PROMPT DEFINITIONS
# =============================================================================
# These combine persona (system) + task (user) prompts for playground use

COMPOSITE_PROMPTS = {
    "forseti-persona-charter": {
        "system_prompt": "forseti.persona",
        "user_prompt": "forseti.charter_validation",
        "description": "Forseti persona + charter validation (for playground)",
    },
    "forseti-persona-category": {
        "system_prompt": "forseti.persona",
        "user_prompt": "forseti.category_classification",
        "description": "Forseti persona + category classification (for playground)",
    },
    "forseti-persona-wording": {
        "system_prompt": "forseti.persona",
        "user_prompt": "forseti.wording_correction",
        "description": "Forseti persona + wording correction (for playground)",
    },
}


def get_opik_client():
    """Get Opik client, return None if not available."""
    try:
        import opik
        return opik.Opik()
    except ImportError:
        _logger.error("OPIK_NOT_INSTALLED: pip install opik")
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


def _get_prompt_content(prompt_name: str) -> Optional[str]:
    """Get the content of a prompt from LOCAL_PROMPTS or JSON_PROMPTS."""
    # Check JSON prompts first (they have messages format)
    if prompt_name in JSON_PROMPTS:
        json_data = JSON_PROMPTS[prompt_name]
        messages = json_data.get("messages", [])
        if messages:
            # Return content from the first message matching the type
            prompt_type = json_data.get("type", "user")
            for msg in messages:
                if msg.get("role") == prompt_type or msg.get("role") == "system":
                    return msg.get("content", "")
            # Fallback: return first message content
            return messages[0].get("content", "")

    # Check LOCAL_PROMPTS
    if prompt_name in LOCAL_PROMPTS:
        prompt_data = LOCAL_PROMPTS[prompt_name]
        # Check for messages format
        if "messages" in prompt_data and prompt_data["messages"]:
            return prompt_data["messages"][0].get("content", "")
        # Fallback to template
        return prompt_data.get("template", "")

    return None


def _get_prompt_variables(prompt_name: str) -> List[str]:
    """Get the variables from a prompt."""
    if prompt_name in JSON_PROMPTS:
        return JSON_PROMPTS[prompt_name].get("variables", [])
    if prompt_name in LOCAL_PROMPTS:
        return LOCAL_PROMPTS[prompt_name].get("variables", [])
    return []


def _update_json_prompt_file(
    prompt_name: str,
    new_content: str,
    opik_commit: str,
    performance: Optional[Dict[str, Any]] = None,
    json_file: str = "forseti_charter.json",
) -> bool:
    """
    Update a single prompt's message content in the local JSON file.

    Args:
        prompt_name: Prompt key (e.g., "forseti.persona")
        new_content: New message content to write
        opik_commit: Opik commit hash to store
        performance: Optional performance metadata to store
        json_file: JSON filename in prompts/local/

    Returns:
        True if content actually changed, False if already up to date
    """
    filepath = PROMPTS_DIR / json_file
    if not filepath.exists():
        _logger.error("JSON_FILE_NOT_FOUND", path=str(filepath))
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if prompt_name not in data:
        _logger.error("PROMPT_NOT_IN_JSON", name=prompt_name, file=json_file)
        return False

    prompt_entry = data[prompt_name]
    messages = prompt_entry.get("messages", [])
    if not messages:
        _logger.error("NO_MESSAGES_IN_PROMPT", name=prompt_name)
        return False

    # Find the message to update based on prompt type
    prompt_type = prompt_entry.get("type", "user")
    target_role = "system" if prompt_type == "system" else "user"

    old_content = None
    for msg in messages:
        if msg.get("role") == target_role:
            old_content = msg.get("content", "")
            break

    if old_content is None:
        # Fallback: update first message
        old_content = messages[0].get("content", "")

    # Check if content actually changed
    if old_content == new_content and prompt_entry.get("opik_commit") == opik_commit:
        return False

    # Update the message content
    for msg in messages:
        if msg.get("role") == target_role:
            msg["content"] = new_content
            break
    else:
        messages[0]["content"] = new_content

    # Update opik_commit
    prompt_entry["opik_commit"] = opik_commit

    # Update performance metadata if provided
    if performance is not None:
        prompt_entry["performance"] = performance

    # Write back
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    _logger.info(
        "JSON_PROMPT_UPDATED",
        name=prompt_name,
        commit=opik_commit,
        file=json_file,
    )
    return True


def build_composite_prompt(composite_name: str) -> Optional[Dict[str, Any]]:
    """
    Build a composite chat prompt from system + user prompts.

    Args:
        composite_name: Name of the composite prompt from COMPOSITE_PROMPTS

    Returns:
        Dict with messages array and metadata, or None if not found
    """
    if composite_name not in COMPOSITE_PROMPTS:
        _logger.error("COMPOSITE_NOT_FOUND", name=composite_name)
        return None

    config = COMPOSITE_PROMPTS[composite_name]
    system_name = config["system_prompt"]
    user_name = config["user_prompt"]

    # Get content from individual prompts
    system_content = _get_prompt_content(system_name)
    user_content = _get_prompt_content(user_name)

    if not system_content:
        _logger.error("SYSTEM_PROMPT_NOT_FOUND", name=system_name)
        return None

    if not user_content:
        _logger.error("USER_PROMPT_NOT_FOUND", name=user_name)
        return None

    # Combine variables (user prompt variables are the input)
    user_variables = _get_prompt_variables(user_name)

    # Build chat messages
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

    return {
        "messages": messages,
        "variables": user_variables,
        "description": config.get("description", ""),
        "components": {
            "system": system_name,
            "user": user_name,
        },
    }


def sync_composite_prompt_to_opik(
    name: str,
    client=None,
) -> Dict[str, Any]:
    """
    Sync a composite prompt (chat format) to Opik.

    Uses create_chat_prompt() for proper chat type prompts.

    Args:
        name: Composite prompt name
        client: Optional Opik client

    Returns:
        Dict with sync result
    """
    if client is None:
        client = get_opik_client()

    if client is None:
        return {"success": False, "name": name, "error": "Opik not available"}

    composite = build_composite_prompt(name)
    if not composite:
        return {"success": False, "name": name, "error": "Failed to build composite"}

    try:
        # Use create_chat_prompt for chat type prompts
        # Messages must be a list of dicts with role/content
        messages = composite["messages"]

        metadata = {
            "variables": composite["variables"],
            "description": composite["description"],
            "components": composite["components"],
            "synced_at": datetime.now().isoformat(),
            "source": "ocapistaine",
            "auto_generated": True,
        }

        # Use create_chat_prompt for proper chat format
        prompt = client.create_chat_prompt(
            name=name,
            messages=messages,
            metadata=metadata,
        )

        commit_id = getattr(prompt, "commit", None)

        _logger.info(
            "COMPOSITE_SYNCED",
            name=name,
            commit=commit_id,
            components=composite["components"],
        )

        return {
            "success": True,
            "name": name,
            "commit": commit_id,
            "components": composite["components"],
        }

    except Exception as e:
        _logger.error("COMPOSITE_SYNC_FAILED", name=name, error=str(e))
        return {
            "success": False,
            "name": name,
            "error": str(e),
        }


def pull_composite_from_opik(
    composite_name: str,
    client=None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Pull an optimized composite prompt from Opik, decompose into
    individual prompts, and update local JSON file.

    Args:
        composite_name: Name of the composite prompt (e.g., "forseti-persona-category")
        client: Optional Opik client
        dry_run: If True, show what would change without writing

    Returns:
        Dict with pull result: pulled name, commit, changed prompts, warnings
    """
    if client is None:
        client = get_opik_client()

    if client is None:
        return {"success": False, "name": composite_name, "error": "Opik not available"}

    if composite_name not in COMPOSITE_PROMPTS:
        return {"success": False, "name": composite_name, "error": f"Unknown composite: {composite_name}"}

    config = COMPOSITE_PROMPTS[composite_name]
    system_name = config["system_prompt"]
    user_name = config["user_prompt"]

    try:
        # Fetch the composite prompt from Opik
        prompt = client.get_chat_prompt(name=composite_name)
        template = getattr(prompt, "template", None)
        commit = getattr(prompt, "commit", None)

        if not template:
            return {"success": False, "name": composite_name, "error": "No template in Opik prompt"}

        # Extract messages from template
        messages = template if isinstance(template, list) else []
        if not messages or len(messages) < 2:
            return {"success": False, "name": composite_name, "error": f"Expected 2+ messages, got {len(messages)}"}

        # Extract content: messages[0] = system, messages[1] = user
        system_msg = messages[0]
        user_msg = messages[1]

        opik_system_content = system_msg.get("content", "") if isinstance(system_msg, dict) else getattr(system_msg, "content", "")
        opik_user_content = user_msg.get("content", "") if isinstance(user_msg, dict) else getattr(user_msg, "content", "")

        # Compare with current local content
        local_system_content = _get_prompt_content(system_name)
        local_user_content = _get_prompt_content(user_name)

        changed = []
        warnings = []

        system_changed = opik_system_content != local_system_content
        user_changed = opik_user_content != local_user_content

        if system_changed:
            changed.append(system_name)
            # Warn: system prompt is shared across all composites
            other_composites = [
                n for n, c in COMPOSITE_PROMPTS.items()
                if c["system_prompt"] == system_name and n != composite_name
            ]
            if other_composites:
                warnings.append(
                    f"Shared prompt '{system_name}' changed — also used by: {', '.join(other_composites)}"
                )

        if user_changed:
            changed.append(user_name)

        if dry_run:
            return {
                "success": True,
                "name": composite_name,
                "commit": commit,
                "changed": changed,
                "warnings": warnings,
                "dry_run": True,
            }

        # Apply changes to local JSON
        if system_changed:
            _update_json_prompt_file(system_name, opik_system_content, commit)
        if user_changed:
            _update_json_prompt_file(user_name, opik_user_content, commit)

        if changed:
            _logger.info(
                "COMPOSITE_PULLED",
                name=composite_name,
                commit=commit,
                changed=changed,
                warnings=warnings,
            )
        else:
            _logger.info("COMPOSITE_UP_TO_DATE", name=composite_name, commit=commit)

        return {
            "success": True,
            "name": composite_name,
            "commit": commit,
            "changed": changed,
            "warnings": warnings,
        }

    except Exception as e:
        _logger.error("COMPOSITE_PULL_FAILED", name=composite_name, error=str(e))
        return {
            "success": False,
            "name": composite_name,
            "error": str(e),
        }


def pull_all_composites(dry_run: bool = False) -> Dict[str, Any]:
    """
    Pull all composite prompts from Opik and update locals.

    Args:
        dry_run: If True, show what would change without writing

    Returns:
        Dict with aggregated results
    """
    client = get_opik_client()
    if client is None:
        return {
            "pulled": [],
            "failed": list(COMPOSITE_PROMPTS.keys()),
            "total": len(COMPOSITE_PROMPTS),
            "error": "Opik not available",
        }

    pulled = []
    failed = []

    for name in COMPOSITE_PROMPTS.keys():
        result = pull_composite_from_opik(name, client=client, dry_run=dry_run)

        if result.get("success"):
            pulled.append(result)
        else:
            failed.append(result)

    total = len(pulled) + len(failed)
    _logger.info(
        "PULL_ALL_COMPLETE",
        pulled=len(pulled),
        failed=len(failed),
        total=total,
        dry_run=dry_run,
    )

    return {
        "pulled": pulled,
        "failed": failed,
        "total": total,
    }


def sync_all_composites(
    filter_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Sync all composite prompts to Opik.

    Args:
        filter_names: Optional list of composite names to sync

    Returns:
        Dict with results
    """
    client = get_opik_client()
    if client is None:
        return {
            "synced": [],
            "failed": list(COMPOSITE_PROMPTS.keys()),
            "total": len(COMPOSITE_PROMPTS),
            "error": "Opik not available",
        }

    synced = []
    failed = []

    for name in COMPOSITE_PROMPTS.keys():
        if filter_names and name not in filter_names:
            continue

        result = sync_composite_prompt_to_opik(name, client=client)

        if result["success"]:
            synced.append(result)
        else:
            failed.append(result)

    total = len(synced) + len(failed)
    _logger.info(
        "COMPOSITES_SYNC_COMPLETE",
        synced=len(synced),
        failed=len(failed),
        total=total,
    )

    return {
        "synced": synced,
        "failed": failed,
        "total": total,
    }


def get_composite_performance(
    composite_name: str,
    client=None,
) -> Dict[str, Any]:
    """
    Get latest performance data for a composite prompt from Opik experiments.

    Fetches the prompt from Opik to get its internal ID, then queries
    experiments linked to that prompt via the REST API. Falls back to
    searching experiments by the dataset_prefix from AGENT_FEATURE_REGISTRY.

    Args:
        composite_name: Name of the composite prompt
        client: Optional Opik client

    Returns:
        Dict with scores, provider, model, evaluated_at
    """
    if client is None:
        client = get_opik_client()

    if client is None:
        return {"success": False, "prompt": composite_name, "error": "Opik not available"}

    try:
        experiments_data = []

        # Strategy 1: Find experiments linked to this prompt via prompt_id
        try:
            prompt = client.get_chat_prompt(name=composite_name)
            prompt_id = getattr(prompt, "__internal_api__prompt_id__", None)
            if prompt_id:
                page = client._rest_client.experiments.find_experiments(
                    prompt_id=prompt_id, size=10
                )
                experiments_data = page.content or []
        except Exception:
            pass

        # Strategy 2: Search experiments by experiment_type from AGENT_FEATURE_REGISTRY
        # Experiment names follow: "{experiment_type}-eval-{YYYYMMDD}-{HHMMSS}"
        if not experiments_data:
            config = COMPOSITE_PROMPTS.get(composite_name, {})
            user_prompt_name = config.get("user_prompt", "")

            # Find matching registry entry by prompt_key
            from app.services.tasks import AGENT_FEATURE_REGISTRY

            experiment_type = None
            for exp_type, feat_config in AGENT_FEATURE_REGISTRY.items():
                if feat_config.get("prompt_key") == user_prompt_name:
                    experiment_type = exp_type
                    break

            if experiment_type:
                try:
                    found = client.get_experiments_by_name(experiment_type)
                    # get_experiments_by_name returns Experiment objects, get full data
                    for exp in found:
                        exp_data = exp.get_experiment_data()
                        experiments_data.append(exp_data)
                except Exception:
                    pass

        if not experiments_data:
            return {
                "success": True,
                "prompt": composite_name,
                "scores": {},
                "message": "No experiments found",
            }

        # Sort by created_at descending, pick latest
        experiments_data.sort(
            key=lambda e: getattr(e, "created_at", None) or datetime.min,
            reverse=True,
        )
        latest = experiments_data[0]
        experiment_name = getattr(latest, "name", composite_name)

        # Extract feedback scores (averaged across traces)
        scores = {}
        feedback_scores = getattr(latest, "feedback_scores", None)
        if feedback_scores:
            for score in feedback_scores:
                scores[score.name] = score.value

        # Extract experiment-level scores
        experiment_scores = getattr(latest, "experiment_scores", None)
        if experiment_scores:
            for score in experiment_scores:
                scores[f"exp.{score.name}"] = score.value

        # Extract metadata (stored as JsonListStringPublic)
        raw_metadata = getattr(latest, "metadata", None)
        metadata = {}
        if raw_metadata:
            # JsonListStringPublic may be a list of JSON strings or dicts
            if isinstance(raw_metadata, dict):
                metadata = raw_metadata
            elif isinstance(raw_metadata, list):
                for item in raw_metadata:
                    if isinstance(item, dict):
                        metadata.update(item)
                    elif isinstance(item, str):
                        try:
                            metadata.update(json.loads(item))
                        except (json.JSONDecodeError, TypeError):
                            pass

        provider = metadata.get("task_provider", metadata.get("provider", "unknown"))
        model = metadata.get("task_model", metadata.get("model", "unknown"))
        evaluated_at = getattr(latest, "created_at", None)
        trace_count = getattr(latest, "trace_count", None)

        # Check linked prompt versions
        prompt_versions = getattr(latest, "prompt_versions", None) or []
        linked_commits = [
            getattr(pv, "commit", None) for pv in prompt_versions
        ]

        result = {
            "success": True,
            "prompt": composite_name,
            "experiment": experiment_name,
            "scores": scores,
            "provider": provider,
            "model": model,
            "evaluated_at": str(evaluated_at) if evaluated_at else None,
            "trace_count": trace_count,
            "linked_commits": [c for c in linked_commits if c],
        }

        _logger.info("PERFORMANCE_FETCHED", name=composite_name, scores=scores)
        return result

    except Exception as e:
        _logger.error("PERFORMANCE_FETCH_FAILED", name=composite_name, error=str(e))
        return {
            "success": False,
            "prompt": composite_name,
            "error": str(e),
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

def _print_performance(names: List[str]) -> None:
    """Print performance data for a list of composite prompt names."""
    print("\nPerformance Data:")
    print("-" * 50)
    for name in names:
        perf = get_composite_performance(name)
        if perf.get("success"):
            scores = perf.get("scores", {})
            print(f"  {name}:")
            print(f"    Experiment: {perf.get('experiment', 'N/A')}")
            print(f"    Provider: {perf.get('provider', 'N/A')}")
            print(f"    Model: {perf.get('model', 'N/A')}")
            print(f"    Evaluated: {perf.get('evaluated_at', 'N/A')}")
            trace_count = perf.get("trace_count")
            if trace_count is not None:
                print(f"    Traces: {trace_count}")
            linked = perf.get("linked_commits", [])
            if linked:
                print(f"    Prompt commits: {', '.join(linked)}")
            if scores:
                print(f"    Scores:")
                for k, v in scores.items():
                    print(f"      {k}: {v}")
            else:
                print(f"    Scores: {perf.get('message', 'none')}")
        else:
            print(f"  ❌ {name}: {perf.get('error', 'Unknown error')}")
        print()


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
    parser.add_argument(
        "--composites",
        action="store_true",
        help="Sync composite chat prompts (persona + task)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Sync both individual and composite prompts",
    )
    parser.add_argument(
        "--pull",
        nargs="?",
        const="__all__",
        default=None,
        metavar="NAME",
        help="Pull optimized composite from Opik (name or all if omitted)",
    )
    parser.add_argument(
        "--pull-all",
        action="store_true",
        help="Pull all composite prompts from Opik",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing",
    )
    parser.add_argument(
        "--performance",
        action="store_true",
        help="Fetch and display performance data from experiments",
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

        print("\nComposite Prompts (auto-generated):")
        print("-" * 50)
        for name, config in COMPOSITE_PROMPTS.items():
            print(f"  {name}")
            print(f"    System: {config['system_prompt']}")
            print(f"    User: {config['user_prompt']}")
            print(f"    Description: {config.get('description', '')[:60]}...")
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

    # Handle --pull and --pull-all
    if args.pull is not None or args.pull_all:
        dry_run = args.dry_run
        mode_label = " (dry run)" if dry_run else ""

        if args.pull_all or args.pull == "__all__":
            print(f"\nPulling all composites from Opik{mode_label}...")
            result = pull_all_composites(dry_run=dry_run)

            for item in result.get("pulled", []):
                changed = item.get("changed", [])
                status = "changed" if changed else "up to date"
                print(f"  ✅ {item['name']} ({status}, commit: {item.get('commit', 'N/A')})")
                for c in changed:
                    print(f"     ~ {c}")
                for w in item.get("warnings", []):
                    print(f"     ⚠ {w}")

            for item in result.get("failed", []):
                print(f"  ❌ {item['name']}: {item.get('error', 'Unknown error')}")

            print(f"\n  Pulled: {len(result.get('pulled', []))}")
            print(f"  Failed: {len(result.get('failed', []))}")
            print(f"  Total: {result.get('total', 0)}")
        else:
            composite_name = args.pull
            print(f"\nPulling {composite_name} from Opik{mode_label}...")
            result = pull_composite_from_opik(composite_name, dry_run=dry_run)

            if result.get("success"):
                changed = result.get("changed", [])
                status = "changed" if changed else "up to date"
                print(f"  ✅ {result['name']} ({status}, commit: {result.get('commit', 'N/A')})")
                for c in changed:
                    print(f"     ~ {c}")
                for w in result.get("warnings", []):
                    print(f"     ⚠ {w}")
            else:
                print(f"  ❌ {result.get('name')}: {result.get('error', 'Unknown error')}")

        # Optionally show performance data
        if args.performance:
            names = list(COMPOSITE_PROMPTS.keys()) if (args.pull_all or args.pull == "__all__") else [args.pull]
            _print_performance(names)

        return

    # Standalone --performance (without --pull)
    if args.performance:
        _print_performance(list(COMPOSITE_PROMPTS.keys()))
        return

    # Sync individual prompts (unless --composites only)
    if not args.composites or args.all:
        print("\nSyncing individual prompts to Opik...")
        if args.prefix:
            print(f"Filtering by prefix: {args.prefix}")

        result = sync_all_prompts(filter_prefix=args.prefix)

        print(f"\nIndividual Prompts:")
        print(f"  Synced: {len(result['synced'])}")
        for item in result["synced"]:
            print(f"    ✅ {item['name']} (commit: {item.get('commit', 'N/A')})")

        print(f"  Failed: {len(result['failed'])}")
        for item in result["failed"]:
            print(f"    ❌ {item['name']}: {item.get('error', 'Unknown error')}")

        print(f"  Total: {result['total']}")

    # Sync composite prompts
    if args.composites or args.all:
        print("\nSyncing composite prompts to Opik...")

        composite_result = sync_all_composites()

        print(f"\nComposite Prompts:")
        print(f"  Synced: {len(composite_result['synced'])}")
        for item in composite_result["synced"]:
            components = item.get("components", {})
            print(f"    ✅ {item['name']} (commit: {item.get('commit', 'N/A')})")
            print(f"       = {components.get('system', '?')} + {components.get('user', '?')}")

        print(f"  Failed: {len(composite_result['failed'])}")
        for item in composite_result["failed"]:
            print(f"    ❌ {item['name']}: {item.get('error', 'Unknown error')}")

        print(f"  Total: {composite_result['total']}")


if __name__ == "__main__":
    main()
