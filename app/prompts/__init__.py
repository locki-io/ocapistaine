# app/prompts/__init__.py
"""
Prompt Management Module

Centralized prompt access with versioning, caching, and multi-backend support.

Usage:
    # Simple access
    from app.prompts import get_prompt, format_prompt

    template = get_prompt("forseti.charter_validation")
    formatted = format_prompt("forseti.charter_validation", title="...", body="...")

    # Advanced usage with registry
    from app.prompts import get_registry

    registry = get_registry()
    prompt_info = registry.get_prompt("forseti.persona")
    print(f"Source: {prompt_info.source}, Version: {prompt_info.version}")

    # List available prompts
    forseti_prompts = registry.list_prompts(prefix="forseti.")

Available Prompts:
    forseti.persona              - System prompt for Forseti 461 agent
    forseti.charter_validation   - Validate contribution against charter
    forseti.category_classification - Classify into 7 categories
    forseti.wording_correction   - Suggest wording improvements
    forseti.batch_validation     - Batch validate multiple contributions
    autocontrib.draft_fr         - Generate draft contribution (French)
    autocontrib.draft_en         - Generate draft contribution (English)

Constants:
    CATEGORIES                   - List of 7 charter categories
    CATEGORY_DESCRIPTIONS        - Bilingual category descriptions
    VIOLATIONS_TEXT              - Charter violation rules
    ENCOURAGED_TEXT              - Charter values
"""

from app.prompts.registry import (
    PromptRegistry,
    PromptInfo,
    get_registry,
    get_prompt,
    format_prompt,
)

from app.prompts.constants import (
    CATEGORIES,
    CategoryType,
    CATEGORY_DESCRIPTIONS,
    VIOLATIONS_TEXT,
    ENCOURAGED_TEXT,
    CATEGORIES_TEXT,
    get_category_description,
    get_categories_text,
)

# Lazy imports for optional Opik features
def sync_all_prompts(*args, **kwargs):
    """Sync all prompts to Opik library."""
    from app.prompts.opik_sync import sync_all_prompts as _sync
    return _sync(*args, **kwargs)


def optimize_forseti_charter(*args, **kwargs):
    """Optimize Forseti charter validation prompt."""
    from app.prompts.optimizer import optimize_forseti_charter as _optimize
    return _optimize(*args, **kwargs)


__all__ = [
    # Registry
    "PromptRegistry",
    "PromptInfo",
    "get_registry",
    "get_prompt",
    "format_prompt",
    # Constants
    "CATEGORIES",
    "CategoryType",
    "CATEGORY_DESCRIPTIONS",
    "VIOLATIONS_TEXT",
    "ENCOURAGED_TEXT",
    "CATEGORIES_TEXT",
    "get_category_description",
    "get_categories_text",
    # Opik Integration
    "sync_all_prompts",
    "optimize_forseti_charter",
]
