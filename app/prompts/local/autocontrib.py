# app/prompts/local/autocontrib.py
"""
Auto-Contribution Workflow Prompts (Local Fallback)

These prompts generate draft contributions for citizens.
The canonical versions are stored in Opik Prompt Library.
"""

# =============================================================================
# DRAFT GENERATION PROMPTS
# =============================================================================

DRAFT_PROMPT_FR = """Tu es un assistant qui aide les citoyens d'Audierne à rédiger des contributions constructives pour la consultation citoyenne.

DOCUMENT SOURCE{source_title_section}:
{source_text}

CATÉGORIE CHOISIE: {category} ({category_desc})

Génère une contribution citoyenne au format Framaforms qui soit:
- Constructive et respectueuse
- Basée sur le document source
- Concrète et locale (spécifique à Audierne)
- Sans attaques personnelles ni discrimination

La contribution doit avoir:

1. CONSTAT FACTUEL (2-3 phrases):
   - Une observation concrète sur la situation actuelle
   - Basée sur des faits ou des observations locales
   - Neutre et factuelle

2. IDÉES D'AMÉLIORATIONS (3-4 phrases):
   - Des propositions concrètes et réalisables
   - En lien avec le constat
   - Constructives pour la commune

Réponds en JSON:
{{
  "constat_factuel": "...",
  "idees_ameliorations": "..."
}}

Réponds UNIQUEMENT avec le JSON."""


DRAFT_PROMPT_EN = """You are an assistant helping citizens of Audierne write constructive contributions for the civic consultation.

SOURCE DOCUMENT{source_title_section}:
{source_text}

CHOSEN CATEGORY: {category} ({category_desc})

Generate a citizen contribution in Framaforms format that is:
- Constructive and respectful
- Based on the source document
- Concrete and local (specific to Audierne)
- Without personal attacks or discrimination

The contribution should have:

1. FACTUAL OBSERVATION (2-3 sentences):
   - A concrete observation about the current situation
   - Based on facts or local observations
   - Neutral and factual

2. IMPROVEMENT IDEAS (3-4 sentences):
   - Concrete and achievable proposals
   - Related to the observation
   - Constructive for the municipality

Reply in JSON:
{{
  "constat_factuel": "...",
  "idees_ameliorations": "..."
}}

Reply ONLY with the JSON."""


# =============================================================================
# PROMPT METADATA (For Registry)
# =============================================================================

PROMPTS = {
    "autocontrib.draft_fr": {
        "template": DRAFT_PROMPT_FR,
        "type": "user",
        "variables": ["source_text", "source_title_section", "category", "category_desc"],
        "description": "Generate draft contribution in French",
        "language": "fr",
    },
    "autocontrib.draft_en": {
        "template": DRAFT_PROMPT_EN,
        "type": "user",
        "variables": ["source_text", "source_title_section", "category", "category_desc"],
        "description": "Generate draft contribution in English",
        "language": "en",
    },
}


def get_draft_prompt(language: str = "fr") -> str:
    """Get draft prompt for specified language."""
    if language == "en":
        return DRAFT_PROMPT_EN
    return DRAFT_PROMPT_FR


def format_draft_prompt(
    source_text: str,
    category: str,
    category_desc: str,
    source_title: str = "",
    language: str = "fr",
) -> str:
    """Format draft prompt with variables."""
    template = get_draft_prompt(language)
    source_title_section = f" - {source_title}" if source_title else ""

    return template.format(
        source_text=source_text[:3000],  # Limit source text
        source_title_section=source_title_section,
        category=category.capitalize(),
        category_desc=category_desc,
    )
