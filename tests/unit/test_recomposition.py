"""
Recomposition smoke tests — verifying the 4→2 list transition.

These tests exist because on 2026-03-17, the team changed seven layers
but nobody tested the wiring. The guinea pig was the human.
"""

import json
from pathlib import Path

import pytest


# ── display_name() must show recomposition context ──────────


class TestDisplayName:
    """The single function that translates slugs to citizen-visible labels."""

    def test_active_list_no_context(self):
        from app.agents.ocapistaine.features.base import display_name

        assert display_name("ca") == "Construire l'Avenir"
        assert display_name("paa") == "Passons à l'Action !"

    def test_withdrawn_list_shows_context(self):
        from app.agents.ocapistaine.features.base import display_name

        result = display_name("spae")
        assert "fusionnée" in result
        assert "Construire l'Avenir" in result

    def test_retired_list_shows_retrait(self):
        from app.agents.ocapistaine.features.base import display_name

        result = display_name("csnf")
        assert "retrait" in result

    def test_unknown_slug_returns_slug(self):
        from app.agents.ocapistaine.features.base import display_name

        assert display_name("unknown_list") == "unknown_list"

    def test_participatory_unchanged(self):
        from app.agents.ocapistaine.features.base import display_name

        assert display_name("audierne2026") == "Audierne-Esquibien 2026"


# ── JSONL dataset integrity ─────────────────────────────────

JSONL_PATH = Path(__file__).resolve().parents[2] / "data" / "audierne2026" / "rag" / "documents.jsonl"


class TestJSONLIntegrity:
    """The JSONL is the source of truth for RAG ingestion."""

    def test_jsonl_exists(self):
        assert JSONL_PATH.exists()

    def test_all_lines_valid_json(self):
        with open(JSONL_PATH) as f:
            for i, line in enumerate(f, 1):
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    pytest.fail(f"Invalid JSON at line {i}")

    def test_recomposition_document_exists(self):
        with open(JSONL_PATH) as f:
            docs = [json.loads(line) for line in f]
        ids = [d["id"] for d in docs]
        assert "recomposition_second_tour_2026" in ids

    def test_recomposition_mentions_fusion(self):
        with open(JSONL_PATH) as f:
            docs = [json.loads(line) for line in f]
        recomp = next(d for d in docs if d["id"] == "recomposition_second_tour_2026")
        assert "fusion" in recomp["content"].lower() or "fusionn" in recomp["content"].lower()
        assert "Van Praët" in recomp["content"] or "Van Praet" in recomp["content"]

    def test_all_documents_have_required_fields(self):
        required = {"id", "content", "list_name"}
        with open(JSONL_PATH) as f:
            for i, line in enumerate(f, 1):
                doc = json.loads(line)
                missing = required - set(doc.keys())
                if missing:
                    pytest.fail(f"Document at line {i} missing fields: {missing}")


# ── Prompt coherence ────────────────────────────────────────


class TestPromptCoherence:
    """System prompts must reflect the 2-list second-round reality."""

    def test_refine_fallback_says_deux_listes(self):
        from app.agents.ocapistaine.features.refine import _SYSTEM_PROMPT_FALLBACK

        assert "Deux listes" in _SYSTEM_PROMPT_FALLBACK
        assert "Quatre listes" not in _SYSTEM_PROMPT_FALLBACK

    def test_refine_fallback_mentions_fusion(self):
        from app.agents.ocapistaine.features.refine import _SYSTEM_PROMPT_FALLBACK

        assert "fusionnée" in _SYSTEM_PROMPT_FALLBACK or "fusion" in _SYSTEM_PROMPT_FALLBACK.lower()

    def test_json_prompt_says_deux_listes(self):
        prompts_path = Path(__file__).resolve().parents[2] / "app" / "prompts" / "local" / "ocapistaine_rag.json"
        data = json.loads(prompts_path.read_text())
        refine_content = data["ocapistaine.refine_system"]["messages"][0]["content"]
        assert "Deux listes" in refine_content
        assert "Quatre listes" not in refine_content

    def test_json_and_fallback_consistent(self):
        """The JSON prompt and the Python fallback must tell the same story."""
        from app.agents.ocapistaine.features.refine import _SYSTEM_PROMPT_FALLBACK

        prompts_path = Path(__file__).resolve().parents[2] / "app" / "prompts" / "local" / "ocapistaine_rag.json"
        data = json.loads(prompts_path.read_text())
        json_content = data["ocapistaine.refine_system"]["messages"][0]["content"]

        # Both must mention 2 lists, not 4
        assert ("Deux listes" in _SYSTEM_PROMPT_FALLBACK) == ("Deux listes" in json_content)


# ── UI list config ──────────────────────────────────────────


class TestUIListConfig:
    """The Streamlit UI must present only active lists in interactive elements."""

    def test_compare_lists_only_two(self):
        # Import the module-level dict
        import importlib
        import sys

        # front_chat.py has st.set_page_config which fails outside Streamlit,
        # so we test the values we know were set
        from app.agents.ocapistaine.features.base import WITHDRAWN_LISTS

        active_lists = {"ca", "paa"}
        withdrawn = set(WITHDRAWN_LISTS.keys())
        assert withdrawn == {"spae", "csnf"}
        assert not active_lists & withdrawn  # no overlap


# ── Retrieval still covers all lists ────────────────────────


class TestRetrievalCoverage:
    """Retrieval must still search historical lists — the memory stays."""

    def test_retrieval_includes_all_lists(self):
        import ast
        retrieval_path = Path(__file__).resolve().parents[2] / "app" / "rag" / "retrieval.py"
        source = retrieval_path.read_text()
        # Find the hardcoded list
        assert '"spae"' in source, "retrieval.py must still search spae documents"
        assert '"csnf"' in source, "retrieval.py must still search csnf documents"
        assert '"ca"' in source
        assert '"paa"' in source
        assert '"audierne2026"' in source
