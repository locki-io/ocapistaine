# app/prompts/local/__init__.py
"""
Local Prompt Fallbacks

Supports both Python (.py) and JSON (.json) prompt formats.
JSON prompts use chat format (OpenAI-compatible) with Mustache variables.
"""

from app.prompts.local.forseti import PROMPTS as FORSETI_PROMPTS_PY
from app.prompts.local.autocontrib import PROMPTS as AUTOCONTRIB_PROMPTS
from app.prompts.local.json_loader import (
    JSON_PROMPTS,
    load_json_prompts,
    get_prompt_content,
    get_messages,
    format_prompt,
    format_messages,
)

# Combine all local prompts
# JSON prompts take priority (newer Opik-synced versions)
LOCAL_PROMPTS = {
    **FORSETI_PROMPTS_PY,  # Python fallback
    **AUTOCONTRIB_PROMPTS,
    **{
        name: {
            "template": get_prompt_content(data),
            "messages": data.get("messages", []),
            "type": data.get("type", "user"),
            "format": data.get("format", "chat"),
            "variables": data.get("variables", []),
            "description": data.get("description", ""),
            "opik_name": data.get("name"),
            "opik_commit": data.get("opik_commit"),
        }
        for name, data in JSON_PROMPTS.items()
    },
}

__all__ = [
    "LOCAL_PROMPTS",
    "JSON_PROMPTS",
    "load_json_prompts",
    "get_prompt_content",
    "get_messages",
    "format_prompt",
    "format_messages",
]
