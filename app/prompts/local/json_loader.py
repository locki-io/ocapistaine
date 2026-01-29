# app/prompts/local/json_loader.py
"""
JSON Prompt Loader

Loads prompts from JSON files in chat format (OpenAI-compatible).
Supports both Mustache ({{var}}) and Python ({var}) variable formats.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

# Directory containing JSON prompt files
PROMPTS_DIR = Path(__file__).parent


def load_json_prompts(filename: str = "forseti_charter.json") -> Dict[str, Dict[str, Any]]:
    """
    Load prompts from a JSON file.

    Args:
        filename: JSON file name in the local/ directory

    Returns:
        Dict mapping prompt names to prompt data
    """
    filepath = PROMPTS_DIR / filename
    if not filepath.exists():
        return {}

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_prompt_content(prompt_data: Dict[str, Any]) -> str:
    """
    Extract the prompt content from chat format.

    Args:
        prompt_data: Prompt data dict with 'messages' key

    Returns:
        Combined content string
    """
    messages = prompt_data.get("messages", [])
    if not messages:
        return prompt_data.get("template", "")

    # For single message, return content directly
    if len(messages) == 1:
        return messages[0].get("content", "")

    # For multiple messages, combine with role prefixes
    parts = []
    for msg in messages:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        parts.append(f"[{role}]\n{content}")

    return "\n\n".join(parts)


def get_messages(prompt_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Get messages array from prompt data.

    Args:
        prompt_data: Prompt data dict

    Returns:
        List of message dicts with 'role' and 'content'
    """
    return prompt_data.get("messages", [])


def format_prompt(
    prompt_data: Dict[str, Any],
    variables: Optional[Dict[str, Any]] = None,
    use_mustache: bool = True,
) -> str:
    """
    Format a prompt with variables.

    Args:
        prompt_data: Prompt data dict
        variables: Variables to substitute
        use_mustache: If True, use {{var}} format; else use {var}

    Returns:
        Formatted prompt string
    """
    content = get_prompt_content(prompt_data)
    variables = variables or {}

    if use_mustache:
        # Replace {{input.var}} with value
        for key, value in variables.items():
            # Handle nested keys like input.title
            content = content.replace(f"{{{{input.{key}}}}}", str(value))
            content = content.replace(f"{{{{{key}}}}}", str(value))
    else:
        # Replace {var} with value
        try:
            content = content.format(**variables)
        except KeyError:
            # Partial formatting - replace what we can
            for key, value in variables.items():
                content = content.replace(f"{{{key}}}", str(value))

    return content


def format_messages(
    prompt_data: Dict[str, Any],
    variables: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """
    Format messages with variables, returning chat format.

    Args:
        prompt_data: Prompt data dict
        variables: Variables to substitute

    Returns:
        List of formatted message dicts
    """
    messages = get_messages(prompt_data)
    variables = variables or {}
    formatted = []

    for msg in messages:
        content = msg.get("content", "")

        # Replace Mustache variables
        for key, value in variables.items():
            content = content.replace(f"{{{{input.{key}}}}}", str(value))
            content = content.replace(f"{{{{{key}}}}}", str(value))

        formatted.append({
            "role": msg.get("role", "user"),
            "content": content,
        })

    return formatted


def convert_to_python_format(content: str) -> str:
    """
    Convert Mustache {{var}} to Python {var} format.

    Args:
        content: Prompt content with Mustache variables

    Returns:
        Content with Python format variables
    """
    # {{input.title}} -> {title}
    content = re.sub(r"\{\{input\.(\w+)\}\}", r"{\1}", content)
    # {{var}} -> {var}
    content = re.sub(r"\{\{(\w+)\}\}", r"{\1}", content)
    return content


def convert_to_mustache_format(content: str) -> str:
    """
    Convert Python {var} to Mustache {{input.var}} format.

    Args:
        content: Prompt content with Python variables

    Returns:
        Content with Mustache format variables
    """
    # {title} -> {{input.title}}
    content = re.sub(r"\{(\w+)\}", r"{{input.\1}}", content)
    return content


# =============================================================================
# LOAD ALL JSON PROMPTS
# =============================================================================

def load_all_json_prompts() -> Dict[str, Dict[str, Any]]:
    """
    Load all JSON prompt files from the local directory.

    Returns:
        Combined dict of all prompts
    """
    all_prompts = {}

    for json_file in PROMPTS_DIR.glob("*.json"):
        try:
            prompts = load_json_prompts(json_file.name)
            all_prompts.update(prompts)
        except Exception as e:
            print(f"Warning: Failed to load {json_file}: {e}")

    return all_prompts


# Pre-load JSON prompts
JSON_PROMPTS = load_all_json_prompts()
