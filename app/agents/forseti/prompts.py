"""
Forseti Agent Prompts

System prompt (persona) and feature prompt templates for Forseti 461.

NOTE: This module re-exports prompts from the central app/prompts/ module.
The canonical source is app/prompts/local/forseti.py.
"""

# =============================================================================
# IMPORT FROM CENTRAL PROMPT REGISTRY
# =============================================================================

# Import constants from central location (single source of truth)
from app.prompts.constants import (
    CATEGORIES,
    CATEGORY_DESCRIPTIONS,
    VIOLATIONS_TEXT,
    ENCOURAGED_TEXT,
    CATEGORIES_TEXT,
)

# Import prompts from local fallback (canonical source)
from app.prompts.local.forseti import (
    PERSONA_PROMPT,
    CHARTER_VALIDATION_PROMPT,
    CATEGORY_CLASSIFICATION_PROMPT,
    WORDING_CORRECTION_PROMPT,
    BATCH_VALIDATION_PROMPT,
)
