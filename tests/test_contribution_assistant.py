# tests/test_contribution_assistant.py
"""
Tests for ContributionAssistant
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.processors.workflows.workflow_autocontribution import (
    ContributionAssistant,
    DraftContribution,
    generate_draft_sync,
)
# Import from central prompts module
from app.prompts import CATEGORIES, CATEGORY_DESCRIPTIONS


class TestDraftContribution:
    """Test DraftContribution dataclass."""

    def test_draft_contribution_fields(self):
        """Test DraftContribution dataclass structure."""
        draft = DraftContribution(
            constat_factuel="Test constat factuel",
            idees_ameliorations="Test idees ameliorations",
            category="economie",
            source_title="Test source",
        )
        assert draft.constat_factuel == "Test constat factuel"
        assert draft.idees_ameliorations == "Test idees ameliorations"
        assert draft.category == "economie"
        assert draft.source_title == "Test source"

    def test_draft_contribution_default_source_title(self):
        """Test DraftContribution with default source_title."""
        draft = DraftContribution(
            constat_factuel="Constat",
            idees_ameliorations="Idees",
            category="logement",
        )
        assert draft.source_title == ""


class TestCategoryDescriptions:
    """Test category descriptions configuration."""

    def test_all_categories_have_descriptions(self):
        """Test that all categories have FR and EN descriptions."""
        for category in CATEGORIES:
            assert category in CATEGORY_DESCRIPTIONS
            assert "fr" in CATEGORY_DESCRIPTIONS[category]
            assert "en" in CATEGORY_DESCRIPTIONS[category]

    def test_descriptions_not_empty(self):
        """Test that descriptions are not empty."""
        for category in CATEGORIES:
            assert CATEGORY_DESCRIPTIONS[category]["fr"].strip()
            assert CATEGORY_DESCRIPTIONS[category]["en"].strip()


class TestContributionAssistantSync:
    """Test ContributionAssistant class via sync wrapper."""

    def test_generate_draft_returns_draft_contribution(self):
        """Test that generate_draft returns DraftContribution."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(
                content='{"constat_factuel": "Test constat", "idees_ameliorations": "Test idees"}'
            )
        )
        with patch("app.processors.workflows.workflow_autocontribution.get_provider", return_value=mock_provider):
            draft = generate_draft_sync(
                source_text="Test source text about Audierne port",
                category="economie",
                source_title="Test document",
                language="fr",
                provider_name="gemini",
            )

            assert isinstance(draft, DraftContribution)
            assert draft.constat_factuel == "Test constat"
            assert draft.idees_ameliorations == "Test idees"
            assert draft.category == "economie"
            assert draft.source_title == "Test document"

    def test_generate_draft_uses_default_category_for_invalid(self):
        """Test that invalid category defaults to first category."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(
                content='{"constat_factuel": "Test", "idees_ameliorations": "Test"}'
            )
        )
        with patch("app.processors.workflows.workflow_autocontribution.get_provider", return_value=mock_provider):
            draft = generate_draft_sync(
                source_text="Test text",
                category="invalid_category",
                language="fr",
                provider_name="gemini",
            )

            # Should default to first category
            assert draft.category == CATEGORIES[0]

    def test_generate_draft_handles_json_in_code_block(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(
                content='```json\n{"constat_factuel": "Wrapped constat", "idees_ameliorations": "Wrapped idees"}\n```'
            )
        )
        with patch("app.processors.workflows.workflow_autocontribution.get_provider", return_value=mock_provider):
            draft = generate_draft_sync(
                source_text="Test text",
                category="culture",
                language="en",
                provider_name="gemini",
            )

            assert draft.constat_factuel == "Wrapped constat"
            assert draft.idees_ameliorations == "Wrapped idees"

    def test_generate_draft_handles_error_gracefully(self):
        """Test that errors return empty draft instead of raising."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=Exception("API error"))
        with patch("app.processors.workflows.workflow_autocontribution.get_provider", return_value=mock_provider):
            draft = generate_draft_sync(
                source_text="Test text",
                category="ecologie",
                language="fr",
                provider_name="gemini",
            )

            assert draft.constat_factuel == ""
            assert draft.idees_ameliorations == ""
            assert draft.category == "ecologie"

    def test_generate_draft_french_prompt(self):
        """Test that French language uses French prompt."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(
                content='{"constat_factuel": "Fr", "idees_ameliorations": "Fr"}'
            )
        )
        with patch("app.processors.workflows.workflow_autocontribution.get_provider", return_value=mock_provider):
            generate_draft_sync(
                source_text="Test text",
                category="associations",
                language="fr",
                provider_name="gemini",
            )

            # Verify the prompt was in French
            call_args = mock_provider.complete.call_args
            messages = call_args[0][0]
            prompt = messages[0].content
            assert "citoyen" in prompt.lower() or "audierne" in prompt.lower()

    def test_generate_draft_english_prompt(self):
        """Test that English language uses English prompt."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(
                content='{"constat_factuel": "En", "idees_ameliorations": "En"}'
            )
        )
        with patch("app.processors.workflows.workflow_autocontribution.get_provider", return_value=mock_provider):
            generate_draft_sync(
                source_text="Test text",
                category="jeunesse",
                language="en",
                provider_name="gemini",
            )

            # Verify the prompt was in English
            call_args = mock_provider.complete.call_args
            messages = call_args[0][0]
            prompt = messages[0].content
            assert "citizen" in prompt.lower() or "audierne" in prompt.lower()


class TestGenerateDraftSync:
    """Test synchronous wrapper."""

    def test_generate_draft_sync_returns_draft(self):
        """Test that sync wrapper returns DraftContribution."""
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(
            return_value=MagicMock(
                content='{"constat_factuel": "Sync constat", "idees_ameliorations": "Sync idees"}'
            )
        )

        with patch("app.processors.workflows.workflow_autocontribution.get_provider", return_value=mock_provider):
            draft = generate_draft_sync(
                source_text="Test source",
                category="logement",
                source_title="Test title",
                language="fr",
                provider_name="gemini",
            )

            assert isinstance(draft, DraftContribution)
            assert draft.constat_factuel == "Sync constat"
            assert draft.idees_ameliorations == "Sync idees"
