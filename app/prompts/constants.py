# app/prompts/constants.py
"""
Shared Constants for Prompts and UI

Single source of truth for categories and descriptions used across:
- Forseti agent prompts
- Auto-contribution workflow
- Streamlit UI components
- Opik experiments
"""

from typing import Dict, List, Literal

# =============================================================================
# CATEGORIES (Single Source of Truth)
# =============================================================================

CATEGORIES: List[str] = [
    "economie",
    "logement",
    "culture",
    "ecologie",
    "associations",
    "jeunesse",
    "alimentation-bien-etre-soins",
]

CategoryType = Literal[
    "economie",
    "logement",
    "culture",
    "ecologie",
    "associations",
    "jeunesse",
    "alimentation-bien-etre-soins",
]

# =============================================================================
# CATEGORY DESCRIPTIONS (Bilingual)
# =============================================================================

CATEGORY_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "economie": {
        "fr": "Commerce, tourisme, emploi, port, pêche",
        "en": "Business, tourism, jobs, port, fishing",
        "prompt": "business, port, tourism, local economy",
    },
    "logement": {
        "fr": "Habitat, urbanisme, immobilier",
        "en": "Housing, urban planning, real estate",
        "prompt": "housing, real estate, urban planning",
    },
    "culture": {
        "fr": "Patrimoine, événements, arts, musique",
        "en": "Heritage, events, arts, music",
        "prompt": "heritage, events, arts, traditions",
    },
    "ecologie": {
        "fr": "Environnement, énergie, déchets, biodiversité",
        "en": "Environment, energy, waste, biodiversity",
        "prompt": "environment, sustainability, nature",
    },
    "associations": {
        "fr": "Vie associative, clubs, bénévolat",
        "en": "Community organizations, clubs, volunteering",
        "prompt": "community organizations, clubs",
    },
    "jeunesse": {
        "fr": "Écoles, enfance, activités jeunes",
        "en": "Schools, childhood, youth activities",
        "prompt": "youth, schools, education, children",
    },
    "alimentation-bien-etre-soins": {
        "fr": "Alimentation, santé, bien-être, services médicaux",
        "en": "Food, health, wellness, medical services",
        "prompt": "food, health, wellness, medical",
    },
}

# =============================================================================
# CHARTER TEXTS (For Prompts)
# =============================================================================

VIOLATIONS_TEXT = """NOT ACCEPTED (Charter Violations):
- Personal attacks or discriminatory remarks
- Spam or advertising
- Proposals unrelated to Audierne-Esquibien
- False information"""

ENCOURAGED_TEXT = """ENCOURAGED (Charter Values):
- Concrete and argued proposals
- Constructive criticism
- Questions and requests for clarification
- Sharing of experiences and expertise
- Suggestions for improvement"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_category_description(category: str, language: str = "fr") -> str:
    """Get localized description for a category."""
    return CATEGORY_DESCRIPTIONS.get(category, {}).get(language, category)


def get_categories_text() -> str:
    """Get formatted categories text for prompts."""
    lines = ["CATEGORIES:"]
    for cat in CATEGORIES:
        desc = CATEGORY_DESCRIPTIONS.get(cat, {}).get("prompt", cat)
        lines.append(f"- {cat}: {desc}")
    return "\n".join(lines)


# Pre-built for prompt injection
CATEGORIES_TEXT = get_categories_text()
