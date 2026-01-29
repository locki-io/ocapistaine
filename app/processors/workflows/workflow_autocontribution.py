# app/processors/workflows/workflow_autocontribution.py
"""
Auto-Contribution Workflow - Citizen Contribution Creation with Forseti Validation

A 5-step workflow that guides users through creating charter-compliant contributions:

┌─────────────────────────────────────────────────────────────────────────────┐
│                        AUTO-CONTRIBUTION WORKFLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Step 1: LOAD SOURCES                                                       │
│  ├── list_audierne_docs()      → Load available documents                   │
│  └── read_markdown_input()     → Read selected document content             │
│                                                                             │
│  Step 2: SELECT CATEGORY                                                    │
│  └── CATEGORIES                → 7 charter categories                       │
│                                                                             │
│  Step 3: GENERATE DRAFT                                                     │
│  ├── ContributionAssistant     → LLM provider wrapper                       │
│  ├── generate_draft()          → Async draft generation                     │
│  └── generate_draft_sync()     → Sync wrapper for Streamlit                 │
│                                                                             │
│  Step 4: EDIT CONTRIBUTION                                                  │
│  └── (User edits in UI)        → constat_factuel + idees_ameliorations      │
│                                                                             │
│  Step 5: VALIDATE AND SAVE                                                  │
│  ├── run_forseti_validation()  → Forseti 461 charter validation             │
│  ├── ValidationRecord          → Create storage record                      │
│  └── storage.save_validation() → Persist to Redis                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

Usage:
    from app.processors.workflows import AutoContributionWorkflow

    workflow = AutoContributionWorkflow(provider="gemini")

    # Step 1: Load sources
    sources = workflow.step_1_load_sources()

    # Step 2: (UI selects category)

    # Step 3: Generate draft
    draft = workflow.step_3_generate_draft(
        source_text=content,
        category="economie",
        language="fr"
    )

    # Step 4: (User edits draft)

    # Step 5: Validate and save
    result = workflow.step_5_validate_and_save(
        constat_factuel=edited_constat,
        idees_ameliorations=edited_idees,
        category="economie"
    )
"""

import asyncio
import json
import uuid
from datetime import date
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Literal

from app.providers import get_provider, Message
from app.agents.forseti import CATEGORIES, ForsetiAgent
from app.mockup.field_input import list_audierne_docs, read_markdown_input
from app.mockup.storage import get_storage, ValidationRecord
from app.services import AgentLogger

# =============================================================================
# DATA CLASSES
# =============================================================================

LanguageType = Literal["fr", "en"]
ProviderType = Literal["gemini", "claude", "ollama"]


@dataclass
class DraftContribution:
    """AI-generated draft contribution."""
    constat_factuel: str
    idees_ameliorations: str
    category: str
    source_title: str = ""


@dataclass
class AutoContributionConfig:
    """Configuration for the auto-contribution workflow."""
    provider: ProviderType = "gemini"
    model: Optional[str] = None
    language: LanguageType = "fr"


@dataclass
class AutoContributionResult:
    """Result of the complete workflow."""
    contribution_id: str
    is_valid: bool
    confidence: float
    violations: List[str]
    encouraged_aspects: List[str]
    reasoning: str
    category: str
    constat_factuel: str
    idees_ameliorations: str


# =============================================================================
# CATEGORY DESCRIPTIONS (for UI display)
# =============================================================================

CATEGORY_DESCRIPTIONS = {
    "economie": {
        "fr": "Commerce, tourisme, emploi, port, pêche",
        "en": "Business, tourism, jobs, port, fishing",
    },
    "logement": {
        "fr": "Habitat, urbanisme, immobilier",
        "en": "Housing, urban planning, real estate",
    },
    "culture": {
        "fr": "Patrimoine, événements, arts, musique",
        "en": "Heritage, events, arts, music",
    },
    "ecologie": {
        "fr": "Environnement, énergie, déchets, biodiversité",
        "en": "Environment, energy, waste, biodiversity",
    },
    "associations": {
        "fr": "Vie associative, clubs, bénévolat",
        "en": "Community organizations, clubs, volunteering",
    },
    "jeunesse": {
        "fr": "Écoles, enfance, activités jeunes",
        "en": "Schools, childhood, youth activities",
    },
    "alimentation-bien-etre-soins": {
        "fr": "Alimentation, santé, bien-être, services médicaux",
        "en": "Food, health, wellness, medical services",
    },
}


# =============================================================================
# STEP 1: LOAD SOURCES
# =============================================================================

def step_1_load_sources() -> List[Dict[str, str]]:
    """
    Step 1: Load available source documents for inspiration.

    Returns:
        List of document metadata dicts with 'path', 'title', 'filename' keys.
    """
    return list_audierne_docs()


def load_source_content(path: str) -> str:
    """Load content from a source document path."""
    return read_markdown_input(path)


# =============================================================================
# STEP 2: SELECT CATEGORY
# =============================================================================

def step_2_select_category() -> List[str]:
    """
    Step 2: Get available categories for selection.

    Returns:
        List of 7 charter category strings.
    """
    return CATEGORIES


def get_category_description(category: str, language: LanguageType = "fr") -> str:
    """Get localized description for a category."""
    return CATEGORY_DESCRIPTIONS.get(category, {}).get(language, category)


# =============================================================================
# STEP 3: GENERATE DRAFT
# =============================================================================

class ContributionAssistant:
    """
    LLM-powered assistant for generating draft contributions.

    Unlike FieldInputGenerator (mockup), this is focused on:
    - Single contribution at a time
    - No violation injection (valid only)
    - User-focused draft generation
    - Bilingual output (FR/EN)
    """

    def __init__(
        self,
        provider_name: ProviderType = "gemini",
        model: Optional[str] = None,
    ):
        self._provider_name = provider_name
        self._model = model
        self._provider = get_provider(provider_name, model=model, cache=False)
        self._logger = AgentLogger("contribution_assistant")

    async def generate_draft(
        self,
        source_text: str,
        category: str,
        source_title: str = "",
        language: LanguageType = "fr",
    ) -> DraftContribution:
        """
        Generate a draft contribution based on source text and category.

        Args:
            source_text: Inspiration text (document, article, speech)
            category: One of the 7 categories
            source_title: Title of the source document
            language: Output language ("fr" or "en")

        Returns:
            DraftContribution with constat_factuel and idees_ameliorations
        """
        if category not in CATEGORIES:
            category = CATEGORIES[0]

        category_desc = CATEGORY_DESCRIPTIONS.get(category, {}).get(language, category)

        if language == "fr":
            prompt = self._build_french_prompt(source_text, category, category_desc, source_title)
        else:
            prompt = self._build_english_prompt(source_text, category, category_desc, source_title)

        try:
            messages = [Message(role="user", content=prompt)]
            response = await self._provider.complete(messages, json_mode=True)
            content = response.content.strip()

            # Parse JSON response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content)

            draft = DraftContribution(
                constat_factuel=data.get("constat_factuel", ""),
                idees_ameliorations=data.get("idees_ameliorations", ""),
                category=category,
                source_title=source_title,
            )

            self._logger.info(
                "DRAFT_GENERATED",
                category=category,
                language=language,
                constat_len=len(draft.constat_factuel),
                idees_len=len(draft.idees_ameliorations),
            )

            return draft

        except Exception as e:
            self._logger.error("DRAFT_GENERATION_ERROR", error=str(e))
            return DraftContribution(
                constat_factuel="",
                idees_ameliorations="",
                category=category,
                source_title=source_title,
            )

    def _build_french_prompt(self, source_text: str, category: str, category_desc: str, source_title: str) -> str:
        return f"""Tu es un assistant qui aide les citoyens d'Audierne à rédiger des contributions constructives pour la consultation citoyenne.

DOCUMENT SOURCE{f" - {source_title}" if source_title else ""}:
{source_text[:3000]}

CATÉGORIE CHOISIE: {category.capitalize()} ({category_desc})

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

    def _build_english_prompt(self, source_text: str, category: str, category_desc: str, source_title: str) -> str:
        return f"""You are an assistant helping citizens of Audierne write constructive contributions for the civic consultation.

SOURCE DOCUMENT{f" - {source_title}" if source_title else ""}:
{source_text[:3000]}

CHOSEN CATEGORY: {category.capitalize()} ({category_desc})

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


def _run_async(coro):
    """Run async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


def step_3_generate_draft(
    source_text: str,
    category: str,
    source_title: str = "",
    language: LanguageType = "fr",
    provider_name: ProviderType = "gemini",
    model: Optional[str] = None,
) -> DraftContribution:
    """
    Step 3: Generate a draft contribution using LLM.

    Args:
        source_text: Inspiration text from source document
        category: One of the 7 categories
        source_title: Title of source document
        language: Output language ("fr" or "en")
        provider_name: LLM provider
        model: Optional model override

    Returns:
        DraftContribution with generated text
    """
    assistant = ContributionAssistant(provider_name=provider_name, model=model)
    return _run_async(
        assistant.generate_draft(
            source_text=source_text,
            category=category,
            source_title=source_title,
            language=language,
        )
    )


# Alias for backward compatibility
generate_draft_sync = step_3_generate_draft


# =============================================================================
# STEP 4: EDIT CONTRIBUTION
# =============================================================================

def step_4_edit_contribution(
    draft: DraftContribution,
    edited_constat: Optional[str] = None,
    edited_idees: Optional[str] = None,
) -> DraftContribution:
    """
    Step 4: Apply user edits to draft contribution.

    Args:
        draft: Original draft from step 3
        edited_constat: User-edited constat_factuel (or None to keep original)
        edited_idees: User-edited idees_ameliorations (or None to keep original)

    Returns:
        Updated DraftContribution
    """
    return DraftContribution(
        constat_factuel=edited_constat if edited_constat is not None else draft.constat_factuel,
        idees_ameliorations=edited_idees if edited_idees is not None else draft.idees_ameliorations,
        category=draft.category,
        source_title=draft.source_title,
    )


# =============================================================================
# STEP 5: VALIDATE AND SAVE
# =============================================================================

def run_forseti_validation(
    title: str,
    body: str,
    category: str,
    provider_name: ProviderType = "gemini",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Forseti 461 validation on a contribution.

    Args:
        title: Contribution title
        body: Contribution body
        category: Category for validation
        provider_name: LLM provider
        model: Optional model override

    Returns:
        Dict with is_valid, violations, encouraged_aspects, confidence, reasoning, category
    """
    try:
        provider = get_provider(provider_name, model=model, cache=False)
        agent = ForsetiAgent(provider=provider)

        result = asyncio.run(agent.validate(title=title, body=body, category=category))

        return {
            "success": True,
            "is_valid": result.is_valid,
            "violations": result.violations,
            "encouraged_aspects": result.encouraged_aspects,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "category": result.category,
            "original_category": result.original_category,
        }
    except Exception as e:
        return {
            "success": False,
            "is_valid": True,
            "violations": [],
            "encouraged_aspects": [],
            "confidence": 0.0,
            "reasoning": f"Validation error: {str(e)}",
            "category": category,
        }


def step_5_validate_and_save(
    constat_factuel: str,
    idees_ameliorations: str,
    category: str,
    source_title: str = "",
    provider_name: ProviderType = "gemini",
    model: Optional[str] = None,
) -> AutoContributionResult:
    """
    Step 5: Validate with Forseti 461 and save to Redis.

    Args:
        constat_factuel: Final factual observation text
        idees_ameliorations: Final improvement ideas text
        category: Selected category
        source_title: Source document title (for metadata)
        provider_name: LLM provider for validation
        model: Optional model override

    Returns:
        AutoContributionResult with validation results and contribution ID
    """
    storage = get_storage()
    today = date.today().isoformat()
    contrib_id = f"input_{uuid.uuid4().hex[:12]}"

    # Build body and title
    body = f"**Constat factuel:**\n{constat_factuel}\n\n**Idées d'améliorations:**\n{idees_ameliorations}"
    title = constat_factuel[:80] + ("..." if len(constat_factuel) > 80 else "")

    # Run Forseti validation
    validation = run_forseti_validation(
        title=title,
        body=body,
        category=category,
        provider_name=provider_name,
        model=model,
    )

    # Create and save record
    record = ValidationRecord(
        id=contrib_id,
        date=today,
        title=title,
        body=body,
        category=category,
        constat_factuel=constat_factuel,
        idees_ameliorations=idees_ameliorations,
        source="input",
        is_valid=validation.get("is_valid", True),
        violations=validation.get("violations", []),
        encouraged_aspects=validation.get("encouraged_aspects", []),
        confidence=validation.get("confidence", 0.0),
        reasoning=validation.get("reasoning", ""),
        suggested_category=validation.get("category"),
        provider=provider_name,
        model=model,
    )

    storage.save_validation(record)

    return AutoContributionResult(
        contribution_id=contrib_id,
        is_valid=validation.get("is_valid", True),
        confidence=validation.get("confidence", 0.0),
        violations=validation.get("violations", []),
        encouraged_aspects=validation.get("encouraged_aspects", []),
        reasoning=validation.get("reasoning", ""),
        category=category,
        constat_factuel=constat_factuel,
        idees_ameliorations=idees_ameliorations,
    )


# =============================================================================
# WORKFLOW CLASS (for programmatic use)
# =============================================================================

class AutoContributionWorkflow:
    """
    Orchestrates the 5-step auto-contribution workflow.

    Example:
        workflow = AutoContributionWorkflow(provider="gemini")

        # Load sources
        sources = workflow.load_sources()
        content = workflow.load_source_content(sources[0]["path"])

        # Generate and edit
        draft = workflow.generate_draft(content, "economie")
        edited = workflow.edit(draft, edited_constat="...", edited_idees="...")

        # Validate and save
        result = workflow.validate_and_save(edited)
        print(f"Saved: {result.contribution_id}, Valid: {result.is_valid}")
    """

    def __init__(self, config: Optional[AutoContributionConfig] = None):
        self.config = config or AutoContributionConfig()
        self._logger = AgentLogger("autocontribution_workflow")

    def load_sources(self) -> List[Dict[str, str]]:
        """Step 1: Load available source documents."""
        return step_1_load_sources()

    def load_source_content(self, path: str) -> str:
        """Load content from a source document."""
        return load_source_content(path)

    def get_categories(self) -> List[str]:
        """Step 2: Get available categories."""
        return step_2_select_category()

    def get_category_description(self, category: str) -> str:
        """Get description for a category in current language."""
        return get_category_description(category, self.config.language)

    def generate_draft(
        self,
        source_text: str,
        category: str,
        source_title: str = "",
    ) -> DraftContribution:
        """Step 3: Generate draft contribution."""
        return step_3_generate_draft(
            source_text=source_text,
            category=category,
            source_title=source_title,
            language=self.config.language,
            provider_name=self.config.provider,
            model=self.config.model,
        )

    def edit(
        self,
        draft: DraftContribution,
        edited_constat: Optional[str] = None,
        edited_idees: Optional[str] = None,
    ) -> DraftContribution:
        """Step 4: Apply user edits."""
        return step_4_edit_contribution(draft, edited_constat, edited_idees)

    def validate_and_save(
        self,
        draft: DraftContribution,
        source_title: str = "",
    ) -> AutoContributionResult:
        """Step 5: Validate with Forseti and save."""
        return step_5_validate_and_save(
            constat_factuel=draft.constat_factuel,
            idees_ameliorations=draft.idees_ameliorations,
            category=draft.category,
            source_title=source_title or draft.source_title,
            provider_name=self.config.provider,
            model=self.config.model,
        )
