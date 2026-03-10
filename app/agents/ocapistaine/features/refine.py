"""
Query Refinement & Wording Correction — pre-processes user input before RAG retrieval.

Uses OpenAI (gpt-4o-mini) as a cheap, fast pre-processing step.
Two responsibilities in a single LLM call:
  1. Reformulate vague queries for better retrieval
  2. Correct spelling, grammar, and proper-case known candidate names

Gracefully degrades: returns original question on any error.
"""

import json
import logging
from pathlib import Path

from app.providers.base import Message
from app.prompts.local.json_loader import convert_to_python_format

log = logging.getLogger(__name__)


# ── Name Gazetteer ───────────────────────────────────────
# Loaded once from colistier files at module level.

def _titlecase_name(name: str) -> str:
    """Title-case a name, handling particles like 'Le', 'De', 'Van'."""
    parts = []
    for p in name.split():
        # Already mixed case (e.g., "Jean-Charles") — keep it
        if p[0].isupper() and not p.isupper():
            parts.append(p)
        else:
            parts.append(p.capitalize())
    return " ".join(parts)


def _load_candidate_names() -> list[str]:
    """Extract candidate names from the participons submodule colistier files."""
    import re
    names = set()
    # __file__ = app/agents/ocapistaine/features/refine.py → parents[4] = project root
    programmes_dir = Path(__file__).resolve().parents[4] / "ext_data" / "audierne2026" / "programmes"

    if not programmes_dir.exists():
        log.debug("QueryRefiner: programmes dir not found, name gazetteer empty")
        return []

    for md_file in programmes_dir.rglob("*.md"):
        fname = md_file.name.lower()
        if "colistier" not in fname and "liste_name" not in fname:
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()

                # Format 1: "## Florent Lardic — Colistière" (CA / SPAE)
                if line.startswith("#"):
                    name = line.lstrip("#").strip()
                    name = name.split("—")[0].split("–")[0].strip()
                    # Must look like a person name (starts with uppercase, no special chars)
                    if (2 <= len(name.split()) <= 5
                            and len(name) < 50
                            and not re.search(r'[&<>]', name)
                            and name[0].isalpha()):
                        names.add(name)

                # Format 2: "Bosser Eric" or "Le Grand Berengere" (CSNF — last name first)
                elif re.match(r'^[A-ZÀ-Ü][a-zà-ü]+ [A-ZÀ-Ü]', line) and ":" not in line and "**" not in line:
                    parts = line.split()
                    if 2 <= len(parts) <= 4 and all(len(p) < 20 for p in parts):
                        # First name is last token, rest is last name
                        firstname = parts[-1]
                        lastname = " ".join(parts[:-1])
                        name = _titlecase_name(f"{firstname} {lastname}")
                        names.add(name)

                # Format 3: "Camille RIVIER, 28 ans, ..." (PAA — firstname UPPER, comma-separated)
                elif "," in line and re.search(r'[A-ZÀ-Ü]{2,}', line):
                    part = line.split(",")[0].strip()
                    tokens = part.split()
                    if 2 <= len(tokens) <= 4:
                        name = _titlecase_name(part)
                        names.add(name)

        except Exception:
            continue

    # Well-known heads of list (in case parsing missed them)
    known_heads = [
        "Florent Lardic", "Didier Guillon", "Michel Van Praët", "Eric Bosser",
    ]
    for h in known_heads:
        names.add(h)

    return sorted(names)


_CANDIDATE_NAMES: list[str] = _load_candidate_names()


# ── Prompts (loaded from LOCAL_PROMPTS, with hardcoded fallbacks) ─────────

_SYSTEM_PROMPT_FALLBACK = """Tu es un assistant de pré-traitement de questions pour OCapistaine, un chatbot civique sur les élections municipales d'Audierne-Esquibien 2026.

Quatre listes électorales sont en lice :
- Construire l'Avenir (ca) — tête de liste : Florent Lardic
- Passons à l'Action ! (paa) — tête de liste : Didier Guillon
- S'unir pour Audierne-Esquibien (spae) — tête de liste : Michel Van Praët
- Cap sur Notre Futur (csnf) — tête de liste : Eric Bosser

Tu effectues QUATRE tâches en une seule réponse :

1. **CORRECTION** : corrige l'orthographe, la grammaire, les accents, et surtout les noms propres (candidats, lieux). Utilise la casse correcte pour les noms.
2. **REFORMULATION ET EXPANSION** : reformule la question pour qu'elle soit efficace pour une recherche sémantique dans une base vectorielle. TOUJOURS enrichir avec des termes associés quand un lieu, projet ou candidat est mentionné — même si la question semble déjà précise. Les noms courts ("pierre le lec", "le port") doivent être SYSTÉMATIQUEMENT expansés avec leurs termes associés pour la recherche documentaire. Exemple candidat : "Que propose Bosser ?" → "Que propose Éric Bosser (Cap sur Notre Futur) ?" Exemple lieu : "pierre le lec" → "projet de rénovation de l'école Pierre-Le-Lec, regroupement scolaire".
3. **CATÉGORISATION** : identifie la catégorie thématique principale de la question parmi les catégories suivantes. Si aucune ne correspond clairement, renvoie null.
4. **DÉTECTION DE LISTE** : si la question cible une liste électorale spécifique (via le nom d'un candidat ou le nom de la liste), renvoie le code de la liste (ca, paa, spae, csnf). Si la question porte sur plusieurs listes ou aucune en particulier, renvoie null.

CATÉGORIES THÉMATIQUES :
{categories_text}

NOMS CONNUS DES CANDIDATS :
{names_gazetteer}

LIEUX ET PROJETS CONNUS D'AUDIERNE-ESQUIBIEN :
- École Pierre-Le-Lec : projet de rénovation et regroupement scolaire sur le site du front de mer, programme Petites Villes de Demain
- Port d'Audierne : port de pêche, criée, activité langoustière
- Pointe du Raz, Raz de Sein, rivière du Goyen : patrimoine naturel
- Centre-bourg : commerces, dynamisation, logements vacants
- Halles, marché : vie économique locale

Règles :
- Si c'est un suivi de conversation, résous les références ("eux", "pareil") grâce à l'historique
- Conserve le sens original — ne change pas l'intention de l'utilisateur
- Corrige les noms même s'ils sont écrits sans majuscule ou avec des fautes (ex: "van praet" → "Van Praët", "bosser" → "Bosser" s'il s'agit clairement du candidat)
- Quand un candidat est mentionné, AJOUTE le nom de sa liste dans la reformulation pour enrichir le contexte de recherche
- Quand un lieu ou projet local est mentionné, ENRICHIS la question avec des termes associés pour améliorer la recherche. Exemple : "pierre le lec" → "projet de rénovation de l'école Pierre-Le-Lec, regroupement scolaire, Petites Villes de Demain"
- Pour la catégorie, choisis celle qui correspond le mieux au SUJET de la question. Si la question porte sur un candidat sans thème précis, renvoie null.
- Pour list_code, ne renvoie un code que si la question cible UNE SEULE liste. Les questions comparatives ("que proposent les listes", "comparer") → null.

Réponds UNIQUEMENT en JSON avec ce format exact :
{"query": "la question corrigée et reformulée", "corrections": ["florent lardic → Florent Lardic"], "category": "economie", "list_code": "ca"}

Exemples de reformulation attendue :
- "pierre le lec" → "projet de rénovation de l'école Pierre-Le-Lec, regroupement scolaire, programme Petites Villes de Demain"
- "le port" → "le port d'Audierne, criée, activité de pêche et économie portuaire"
- "bosser ecole" → "Que propose Éric Bosser (Cap sur Notre Futur) pour l'école Pierre-Le-Lec et le regroupement scolaire ?"

Si aucune correction n'est nécessaire, renvoie une liste corrections vide.
Si aucune catégorie ne correspond, renvoie "category": null.
Si la question ne cible pas une liste précise, renvoie "list_code": null.
Réponds UNIQUEMENT avec le JSON, sans markdown ni explication."""

_USER_PROMPT_FALLBACK = """Question originale : {question}"""

_USER_PROMPT_WITH_HISTORY_FALLBACK = """Historique de la conversation :
{history}

Question originale : {question}"""


def _load(name: str, fallback: str) -> str:
    """Load prompt from LOCAL_PROMPTS (synced from Opik), converting Mustache to Python format."""
    try:
        from app.prompts.local import LOCAL_PROMPTS

        if name in LOCAL_PROMPTS:
            data = LOCAL_PROMPTS[name]
            msgs = data.get("messages", [])
            if msgs:
                content = msgs[0].get("content", "")
                if content:
                    return convert_to_python_format(content)
            template = data.get("template", "")
            if template:
                return template
    except Exception:
        pass
    return fallback


REFINE_SYSTEM_PROMPT = _load("ocapistaine.refine_system", _SYSTEM_PROMPT_FALLBACK)
REFINE_USER_PROMPT = _load("ocapistaine.refine_user", _USER_PROMPT_FALLBACK)
REFINE_USER_WITH_HISTORY = _load("ocapistaine.refine_user_with_history", _USER_PROMPT_WITH_HISTORY_FALLBACK)

# Questions shorter than this (words) are likely vague and benefit from refinement
_MIN_WORDS_PRECISE = 5


class RefineResult:
    """Result of query refinement, wording correction, category and list detection."""

    __slots__ = ("query", "corrections", "original", "category", "detected_list")

    def __init__(self, query: str, corrections: list[str], original: str,
                 category: str | None = None, detected_list: str | None = None):
        self.query = query
        self.corrections = corrections
        self.original = original
        self.category = category
        self.detected_list = detected_list

    @property
    def was_refined(self) -> bool:
        """True if the query was semantically reformulated."""
        # Compare ignoring case/punctuation of corrections
        if not self.corrections:
            return self.query != self.original
        # If only wording corrections happened, not refined
        corrected_only = self.original
        for c in self.corrections:
            parts = c.split("→")
            if len(parts) == 2:
                corrected_only = corrected_only.replace(parts[0].strip(), parts[1].strip())
        return self.query.strip() != corrected_only.strip()

    @property
    def was_corrected(self) -> bool:
        return len(self.corrections) > 0


class QueryRefiner:
    """
    Pre-processor that reformulates vague queries and corrects wording
    using OpenAI gpt-4o-mini.

    Cheap (~300 tokens in, ~80 tokens out) and fast (~200-400ms).
    Falls back to the original question on any error.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self._provider = None
        self._model = model
        self._names_gazetteer = ", ".join(_CANDIDATE_NAMES) if _CANDIDATE_NAMES else "(aucun)"
        # Load categories from Forseti's single source of truth
        from app.prompts.constants import CATEGORIES, CATEGORY_DESCRIPTIONS
        self._categories = CATEGORIES
        self._categories_text = "\n".join(
            f"- {cat}: {CATEGORY_DESCRIPTIONS.get(cat, {}).get('fr', cat)}"
            for cat in CATEGORIES
        )
        try:
            from app.providers.openai import OpenAIProvider
            self._provider = OpenAIProvider(model=model)
        except (ValueError, ImportError) as e:
            log.warning("QueryRefiner: OpenAI unavailable (%s), disabled", e)

    @property
    def available(self) -> bool:
        return self._provider is not None

    async def refine(
        self,
        question: str,
        history: list[dict] | None = None,
    ) -> RefineResult:
        """
        Refine and correct a user question for better RAG retrieval.

        Args:
            question: Raw user question
            history: Optional conversation history [{role, content}, ...]

        Returns:
            RefineResult with corrected query, list of corrections, original
        """
        if not self._provider:
            return RefineResult(query=question, corrections=[], original=question)

        # Already precise and no name-like tokens? Skip.
        if (self._is_precise(question)
                and not self._needs_history_resolution(question, history)
                and not self._may_contain_names(question)):
            return RefineResult(query=question, corrections=[], original=question)

        try:
            # Use .replace() for system prompt (safe with single-brace JSON examples)
            system = REFINE_SYSTEM_PROMPT.replace(
                "{names_gazetteer}", self._names_gazetteer
            ).replace(
                "{categories_text}", self._categories_text
            )

            if history and len(history) > 0:
                history_text = "\n".join(
                    f"{'Utilisateur' if h['role'] == 'user' else 'Assistant'}: {h['content'][:200]}"
                    for h in history[-4:]
                )
                user_prompt = REFINE_USER_WITH_HISTORY.format(
                    history=history_text, question=question,
                )
            else:
                user_prompt = REFINE_USER_PROMPT.format(question=question)

            messages = [
                Message(role="system", content=system),
                Message(role="user", content=user_prompt),
            ]

            response = await self._provider.complete(
                messages=messages,
                temperature=0.1,
                max_tokens=200,
                json_mode=True,
            )

            return self._parse_response(response.content, question)

        except Exception as e:
            log.warning("QueryRefiner: error (%s), using original question", e)
            return RefineResult(query=question, corrections=[], original=question)

    def _parse_response(self, content: str, original: str) -> RefineResult:
        """Parse JSON response from the LLM."""
        try:
            data = json.loads(content.strip())
            query = data.get("query", "").strip()
            corrections = data.get("corrections", [])

            # Ensure corrections is a list of strings
            if not isinstance(corrections, list):
                corrections = []
            corrections = [str(c) for c in corrections if c]

            # Parse category (validate against known categories)
            category = data.get("category")
            if category and category not in self._categories:
                log.debug("QueryRefiner: unknown category '%s', ignoring", category)
                category = None

            # Parse list_code (validate against known list codes)
            _VALID_LISTS = {"ca", "paa", "spae", "csnf"}
            list_code = data.get("list_code")
            if list_code and list_code not in _VALID_LISTS:
                log.debug("QueryRefiner: unknown list_code '%s', ignoring", list_code)
                list_code = None

            # Sanity check
            if not query or len(query) > max(len(original) * 5, 300):
                return RefineResult(query=original, corrections=[], original=original)

            if query != original:
                log.info("QueryRefiner: '%s' → '%s' (%d corrections, cat=%s, list=%s)",
                         original[:60], query[:60], len(corrections), category, list_code)

            return RefineResult(query=query, corrections=corrections, original=original,
                                category=category, detected_list=list_code)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.warning("QueryRefiner: parse error (%s), using original", e)
            return RefineResult(query=original, corrections=[], original=original)

    def _is_precise(self, question: str) -> bool:
        """Heuristic: a question with enough words and specificity needs no refinement."""
        words = question.split()
        if len(words) < _MIN_WORDS_PRECISE:
            return False
        specific_markers = [
            "liste", "programme", "proposition", "budget", "urbanisme",
            "école", "logement", "écologie", "transport", "culture",
            "association", "jeunesse", "délibération", "arrêté",
            "commission", "conseil municipal",
        ]
        q_lower = question.lower()
        has_specific = any(m in q_lower for m in specific_markers)
        return len(words) >= 8 or has_specific

    def _needs_history_resolution(
        self, question: str, history: list[dict] | None,
    ) -> bool:
        """Detect follow-up questions that reference prior context."""
        if not history:
            return False
        q_lower = question.lower()
        follow_up_markers = [
            "eux", "elles", "cette liste", "l'autre", "pareil",
            "et pour", "même question", "aussi", "idem", "quoi d'autre",
            "continue", "plus de détails", "développe",
        ]
        return any(m in q_lower for m in follow_up_markers)

    # Local places/projects that benefit from query expansion by the LLM
    _LOCAL_PLACES = [
        "pierre le lec", "pierre-le-lec",
        "goyen", "raz de sein", "pointe du raz",
        "grand-rue", "grand rue", "centre-bourg",
        "halles", "criée", "port d'audierne",
        "petites villes de demain",
    ]

    def _may_contain_names(self, question: str) -> bool:
        """Heuristic: detect if the question mentions candidate names or local places."""
        q_lower = question.lower()
        # Check local places/projects (need expansion for better retrieval)
        if any(place in q_lower for place in self._LOCAL_PLACES):
            return True
        if not _CANDIDATE_NAMES:
            return False
        # Check against lowercased last names and common first names
        for name in _CANDIDATE_NAMES:
            parts = name.lower().split()
            # Match on last name (most distinctive)
            if len(parts) >= 2 and parts[-1] in q_lower:
                return True
            # Match on full name
            if name.lower() in q_lower:
                return True
        return False
