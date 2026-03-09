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

Tu effectues DEUX tâches en une seule réponse :

1. **CORRECTION** : corrige l'orthographe, la grammaire, les accents, et surtout les noms propres (candidats, lieux). Utilise la casse correcte pour les noms.
2. **REFORMULATION** : si la question est vague, reformule-la pour qu'elle soit précise et efficace pour une recherche documentaire. Si elle est déjà précise, garde-la telle quelle.

NOMS CONNUS DES CANDIDATS :
{names_gazetteer}

Règles :
- Si c'est un suivi de conversation, résous les références ("eux", "pareil") grâce à l'historique
- Conserve le sens original — ne change pas l'intention de l'utilisateur
- Corrige les noms même s'ils sont écrits sans majuscule ou avec des fautes (ex: "van praet" → "Van Praët", "bosser" → "Bosser" s'il s'agit clairement du candidat)

Réponds UNIQUEMENT en JSON avec ce format exact :
{"query": "la question corrigée et reformulée", "corrections": ["florent lardic → Florent Lardic", "audierne → Audierne"]}

Si aucune correction n'est nécessaire, renvoie une liste corrections vide.
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
    """Result of query refinement + wording correction."""

    __slots__ = ("query", "corrections", "original")

    def __init__(self, query: str, corrections: list[str], original: str):
        self.query = query
        self.corrections = corrections
        self.original = original

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
            system = REFINE_SYSTEM_PROMPT.replace("{names_gazetteer}", self._names_gazetteer)

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

            # Sanity check
            if not query or len(query) > max(len(original) * 5, 300):
                return RefineResult(query=original, corrections=[], original=original)

            if query != original:
                log.info("QueryRefiner: '%s' → '%s' (%d corrections)",
                         original[:60], query[:60], len(corrections))

            return RefineResult(query=query, corrections=corrections, original=original)

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

    def _may_contain_names(self, question: str) -> bool:
        """Heuristic: detect if the question might mention candidate names."""
        if not _CANDIDATE_NAMES:
            return False
        q_lower = question.lower()
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
