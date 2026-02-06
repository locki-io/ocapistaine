# app/mockup/field_input.py
"""
Field Input Generator - Generate themed mockup contributions from real field data.

Takes real input from municipal campaigns (public hearings, mayor speeches, reports)
and generates themed contributions across all 7 categories for Forseti evaluation.

Workflow:
1. Load markdown input (from audierne2026 docs or direct paste)
2. Extract themes/topics using LLM (Gemini/Claude with reasoning)
3. Generate contributions per category based on extracted themes
4. Save to JSON/Redis for daily experiment
"""

import json
import asyncio
from pathlib import Path
from datetime import date
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.services.logging import MockupLogger
from app.mockup.generator import (
    MockContribution,
    save_contributions,
    load_contributions,
)
from app.providers import get_provider, Message
from app.providers.config import ProviderName, get_recommended_model

# Import categories from Forseti (single source of truth)
from app.agents.forseti import CATEGORIES

# Provider type for field input - use centralized type
ProviderType = ProviderName


def _normalize_category(category: str) -> str:
    """
    Normalize LLM-returned category to match valid CATEGORIES.

    Handles:
    - Accents: économie → economie, écologie → ecologie
    - Underscores: alimentation_bien_etre → alimentation-bien-etre
    - Mixed: alimentation_bien-être_soins → alimentation-bien-etre-soins
    """
    import unicodedata

    # Remove accents via unicode normalization
    normalized = unicodedata.normalize('NFKD', category)
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))

    # Replace underscores with hyphens
    normalized = normalized.replace('_', '-')

    # Lowercase
    return normalized.lower()

# Use case name for this module (used with get_recommended_model)
USE_CASE = "field_input"

_logger = MockupLogger("field_input")

# Path to category themes
THEMES_PATH = Path(__file__).parent / "data" / "category_themes.json"

# Path to audierne2026 docs
AUDIERNE_DOCS_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "docs" / "audierne2026"
)


@dataclass
class ExtractedTheme:
    """A theme extracted from field input."""

    category: str
    theme: str
    keywords: List[str]
    context: str  # Relevant excerpt from input

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "theme": self.theme,
            "keywords": self.keywords,
            "context": self.context,
        }


@dataclass
class FieldInputResult:
    """Result of field input processing."""

    source_file: Optional[str] = None
    source_title: str = ""
    input_length: int = 0
    themes_extracted: int = 0
    contributions_generated: int = 0
    categories_covered: List[str] = field(default_factory=list)
    themes: List[ExtractedTheme] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "source_title": self.source_title,
            "input_length": self.input_length,
            "themes_extracted": self.themes_extracted,
            "contributions_generated": self.contributions_generated,
            "categories_covered": self.categories_covered,
            "themes": [t.to_dict() for t in self.themes],
        }


def load_category_themes() -> Dict[str, Any]:
    """Load category themes configuration."""
    if THEMES_PATH.exists():
        with open(THEMES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"categories": {}}


def list_audierne_docs() -> List[Dict[str, str]]:
    """List available audierne2026 markdown files."""
    docs = []
    if AUDIERNE_DOCS_PATH.exists():
        for md_file in AUDIERNE_DOCS_PATH.glob("*.md"):
            # Read first line as title
            with open(md_file, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                title = (
                    first_line.lstrip("#").strip()
                    if first_line.startswith("#")
                    else md_file.stem
                )

            docs.append(
                {
                    "path": str(md_file),
                    "filename": md_file.name,
                    "title": title,
                }
            )
    return docs


def read_markdown_input(file_path: str) -> str:
    """Read markdown file content."""
    path = Path(file_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


class FieldInputGenerator:
    """
    Generate mockup contributions from field input.

    Uses LLM (Gemini/Claude recommended) to:
    1. Extract relevant themes from input text
    2. Generate realistic contributions for each category
    3. Include both valid and borderline examples

    Gemini 2.5 Flash is recommended for its grounding/search capabilities.
    """

    def __init__(
        self,
        provider: ProviderType = "ollama",
        model: Optional[str] = None,
    ):
        """
        Initialize generator with LLM provider.

        Args:
            provider: Provider to use ("gemini", "claude", "ollama")
            model: Optional model override. If None, uses recommended model for provider.
        """
        self._provider_name = provider
        # Get recommended model for field_input use case, with optional override
        self._model = get_recommended_model(provider, USE_CASE, model)

        # Get provider instance with model override if specified
        if model:
            self._provider = get_provider(provider, cache=False, model=model)
        else:
            self._provider = get_provider(provider)
        self._themes_config = load_category_themes()
        self._logger = MockupLogger("field_input_generator")

    async def extract_themes(self, input_text: str) -> List[ExtractedTheme]:
        """
        Extract relevant themes from input text for each category.

        For long documents, processes in chunks and deduplicates themes.

        Args:
            input_text: Markdown content from field input

        Returns:
            List of extracted themes with category assignments

        Raises:
            RuntimeError: If Ollama provider is not available
        """
        # Check Ollama availability before processing (fail fast)
        if self._provider_name == "ollama":
            if hasattr(self._provider, 'health_check'):
                is_healthy = await self._provider.health_check()
                if not is_healthy:
                    self._logger.error(
                        "PROVIDER_UNAVAILABLE",
                        provider="ollama",
                        host=getattr(self._provider, '_host', 'unknown'),
                        hint="Is Ollama running? Try: ollama serve"
                    )
                    raise RuntimeError(
                        "Ollama is not available. Please ensure Ollama is running (ollama serve) "
                        "and the model is pulled (ollama pull mistral:latest)"
                    )

        # Chunk size for processing (characters)
        # Most LLMs can handle 15-30k chars comfortably
        CHUNK_SIZE = 15000
        CHUNK_OVERLAP = 500  # Overlap to avoid cutting mid-sentence

        categories_config = self._themes_config.get("categories", {})

        # If categories config is empty, use CATEGORIES as fallback
        if not categories_config:
            self._logger.warning("EMPTY_CATEGORIES_CONFIG", using_fallback=True)
            categories_config = {cat: {"label": cat.replace("-", " ").title()} for cat in CATEGORIES}

        # Split text into chunks if needed
        chunks = self._split_into_chunks(input_text, CHUNK_SIZE, CHUNK_OVERLAP)
        self._logger.info("CHUNKING", total_length=len(input_text), chunks=len(chunks))

        all_themes = []

        for i, chunk in enumerate(chunks):
            chunk_themes = await self._extract_themes_from_chunk(
                chunk, categories_config, chunk_index=i, total_chunks=len(chunks)
            )
            all_themes.extend(chunk_themes)

        # Deduplicate themes by category + theme name
        seen = set()
        unique_themes = []
        for theme in all_themes:
            key = (theme.category, theme.theme.lower())
            if key not in seen:
                seen.add(key)
                unique_themes.append(theme)

        self._logger.info("THEMES_EXTRACTED", total=len(all_themes), unique=len(unique_themes))
        return unique_themes

    def _split_into_chunks(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Split text into overlapping chunks, trying to break at paragraph boundaries."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # Try to find a paragraph break near the end
            if end < len(text):
                # Look for double newline (paragraph break) within last 500 chars
                search_start = max(end - 500, start)
                para_break = text.rfind("\n\n", search_start, end)
                if para_break > start:
                    end = para_break + 2  # Include the newlines

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start, accounting for overlap
            start = end - overlap if end < len(text) else len(text)

        return chunks

    async def _extract_themes_from_chunk(
        self,
        chunk: str,
        categories_config: Dict[str, Any],
        chunk_index: int = 0,
        total_chunks: int = 1,
    ) -> List[ExtractedTheme]:
        """Extract themes from a single chunk of text."""
        themes = []

        # Build category labels for prompt
        category_labels = {k: v.get("label", k) for k, v in categories_config.items()}

        prompt = f"""Tu es un assistant qui analyse des documents municipaux pour la commune d'Audierne-Esquibien.

Analyse le texte suivant et identifie les thèmes pertinents pour les catégories de contribution citoyenne.

{"[PARTIE " + str(chunk_index + 1) + "/" + str(total_chunks) + "]" if total_chunks > 1 else ""}

TEXTE À ANALYSER:
{chunk}

CATÉGORIES DISPONIBLES:
{json.dumps(category_labels, ensure_ascii=False, indent=2)}

Pour chaque thème identifié, réponds en JSON avec ce format:
{{
  "themes": [
    {{
      "category": "economie",
      "theme": "renovation_port",
      "keywords": ["port", "rénovation", "tourisme"],
      "context": "extrait pertinent du texte (max 200 caractères)"
    }}
  ]
}}

Instructions:
- Identifie 3-7 thèmes principaux couvrant différentes catégories
- Utilise uniquement les catégories listées ci-dessus
- Le "theme" doit être un identifiant court (snake_case)
- Le "context" doit être un extrait direct du texte analysé
- Réponds UNIQUEMENT avec le JSON valide, sans explication ni markdown"""

        try:
            messages = [Message(role="user", content=prompt)]
            response = await self._provider.complete(messages, json_mode=True)
            content = response.content.strip()

            # Log raw response for debugging
            self._logger.debug("LLM_RESPONSE", chunk=chunk_index, length=len(content))

            # Parse JSON response (provider may have already cleaned it)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            # Clean potential issues
            content = content.strip()

            data = json.loads(content)

            for theme_data in data.get("themes", []):
                raw_category = theme_data.get("category", "")
                # Normalize category (remove accents, replace underscores)
                category = _normalize_category(raw_category)
                # Validate category is in allowed list
                if category in CATEGORIES:
                    theme = ExtractedTheme(
                        category=category,
                        theme=theme_data.get("theme", "unknown"),
                        keywords=theme_data.get("keywords", []),
                        context=theme_data.get("context", "")[:300],  # Limit context length
                    )
                    themes.append(theme)
                else:
                    self._logger.warning(
                        "INVALID_CATEGORY",
                        raw=raw_category,
                        normalized=category,
                        chunk=chunk_index
                    )

            self._logger.info("CHUNK_THEMES", chunk=chunk_index, themes=len(themes))

        except json.JSONDecodeError as e:
            self._logger.error("JSON_PARSE_ERROR", chunk=chunk_index, error=str(e), response=content[:500])
        except Exception as e:
            self._logger.error("THEME_EXTRACTION_ERROR", chunk=chunk_index, error=str(e))

        return themes

    async def generate_contribution(
        self,
        theme: ExtractedTheme,
        source_title: str = "",
        include_violation: bool = False,
        violation_type: Optional[str] = None,
    ) -> Optional[MockContribution]:
        """
        Generate a single contribution based on a theme.

        Args:
            theme: Extracted theme to base contribution on
            include_violation: Whether to inject a violation
            violation_type: Type of violation (subtle_violation, aggressive, off_topic)

        Returns:
            MockContribution or None if generation fails
        """
        category_config = self._themes_config.get("categories", {}).get(
            theme.category, {}
        )

        violation_instruction = ""
        if include_violation and violation_type:
            if violation_type == "subtle_violation":
                violation_instruction = """
IMPORTANT: Injecte une VIOLATION SUBTILE de la charte:
- Utilise un ton condescendant ou sarcastique
- Pose des questions rhétoriques critiques
- Remets en question les compétences des élus de manière indirecte
La contribution doit sembler constructive en surface mais être problématique."""
            elif violation_type == "aggressive":
                violation_instruction = """
IMPORTANT: Injecte une VIOLATION AGRESSIVE de la charte:
- Utilise des MAJUSCULES pour montrer la colère
- Inclus des attaques personnelles contre les élus
- Adopte un ton accusateur et non constructif"""
            elif violation_type == "off_topic":
                violation_instruction = """
IMPORTANT: Injecte un HORS-SUJET:
- Dérive vers la politique nationale
- Mentionne des sujets sans rapport avec Audierne
- Mélange le sujet local avec des polémiques générales"""

        prompt = f"""Tu es un citoyen d'Audierne qui souhaite contribuer à la consultation citoyenne.

CONTEXTE DU THÈME:
- Catégorie: {category_config.get("label", theme.category)}
- Thème: {theme.theme}
- Mots-clés: {", ".join(theme.keywords)}
- Contexte extrait: {theme.context[:500]}

{violation_instruction}

Génère une contribution citoyenne au format Framaforms:

1. CONSTAT FACTUEL (2-3 phrases):
   - Observation concrète sur la situation actuelle à Audierne
   - Basé sur le contexte fourni
   - Factuel et local

2. IDÉES D'AMÉLIORATIONS (3-4 phrases):
   - Propositions concrètes et réalisables
   - En lien avec le constat
   - Constructives pour la commune

Réponds en JSON:
{{
  "constat_factuel": "...",
  "idees_ameliorations": "..."
}}

Réponds UNIQUEMENT avec le JSON."""

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

            # Create MockContribution
            import uuid

            contrib_id = f"field_{theme.category}_{uuid.uuid4().hex[:8]}"

            contribution = MockContribution(
                id=contrib_id,
                category=theme.category,
                constat_factuel=data.get("constat_factuel", ""),
                idees_ameliorations=data.get("idees_ameliorations", ""),
                source="derived",
                expected_valid=not include_violation,
                violations_injected=(
                    [violation_type] if include_violation and violation_type else None
                ),
                metadata={
                    "field_input": True,
                    "theme": theme.theme,
                    "source_title": source_title,
                    "generated_date": date.today().isoformat(),
                    "llm_model": self._model,
                },
            )

            return contribution

        except Exception as e:
            self._logger.error(
                "CONTRIBUTION_GENERATION_ERROR", error=str(e), theme=theme.theme
            )
            return None

    async def process_field_input(
        self,
        input_text: str,
        source_file: Optional[str] = None,
        source_title: str = "",
        contributions_per_theme: int = 2,
        include_violations: bool = True,
    ) -> FieldInputResult:
        """
        Process field input and generate themed contributions.

        Args:
            input_text: Markdown content
            source_file: Path to source file (if any)
            source_title: Title of the source document
            contributions_per_theme: Number of contributions per extracted theme
            include_violations: Whether to include violation examples

        Returns:
            FieldInputResult with generation statistics
        """
        result = FieldInputResult(
            source_file=source_file,
            source_title=source_title,
            input_length=len(input_text),
        )

        self._logger.info(
            "PROCESS_START",
            source=source_file or "direct_input",
            length=len(input_text),
        )

        # Step 1: Extract themes
        themes = await self.extract_themes(input_text)
        result.themes = themes
        result.themes_extracted = len(themes)
        result.categories_covered = list(set(t.category for t in themes))

        if not themes:
            self._logger.warning("NO_THEMES_EXTRACTED")
            return result

        # Step 2: Generate contributions for each theme
        contributions = []

        for theme in themes:
            # Valid contribution
            contrib = await self.generate_contribution(
                theme, source_title, include_violation=False
            )
            if contrib:
                contributions.append(contrib)

            # Additional valid variations if requested
            for _ in range(contributions_per_theme - 1):
                contrib = await self.generate_contribution(
                    theme, source_title, include_violation=False
                )
                if contrib:
                    contributions.append(contrib)

            # Violation examples if requested
            if include_violations:
                for violation_type in ["subtle_violation", "aggressive"]:
                    contrib = await self.generate_contribution(
                        theme,
                        source_title,
                        include_violation=True,
                        violation_type=violation_type,
                    )
                    if contrib:
                        contributions.append(contrib)

        result.contributions_generated = len(contributions)

        # Step 3: Save contributions
        if contributions:
            generator = load_contributions()
            existing_ids = {c.id for c in generator.contributions}

            for contrib in contributions:
                if contrib.id not in existing_ids:
                    generator.contributions.append(contrib)

            save_contributions(generator)
            self._logger.info("CONTRIBUTIONS_SAVED", count=len(contributions))

        self._logger.info(
            "PROCESS_COMPLETE",
            themes=result.themes_extracted,
            contributions=result.contributions_generated,
            categories=result.categories_covered,
        )

        return result


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


def process_field_input_sync(
    input_text: str,
    source_file: Optional[str] = None,
    source_title: str = "",
    provider: ProviderType = "ollama",
    model: Optional[str] = None,
    contributions_per_theme: int = 2,
    include_violations: bool = True,
) -> FieldInputResult:
    """
    Synchronous wrapper for processing field input.

    Args:
        input_text: Markdown content
        source_file: Path to source file
        source_title: Title of source document
        provider: LLM provider ("gemini", "claude", "ollama")
        model: Optional model override
        contributions_per_theme: Contributions per theme
        include_violations: Include violation examples

    Returns:
        FieldInputResult
    """
    generator = FieldInputGenerator(provider=provider, model=model)
    return _run_async(
        generator.process_field_input(
            input_text=input_text,
            source_file=source_file,
            source_title=source_title,
            contributions_per_theme=contributions_per_theme,
            include_violations=include_violations,
        )
    )
