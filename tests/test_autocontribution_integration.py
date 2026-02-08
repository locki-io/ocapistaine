# tests/test_questions_integration.py
"""
Integration tests for Questions tab workflow.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from app.processors.workflows.workflow_autocontribution import DraftContribution
from app.mockup.storage import ValidationRecord, get_storage


class TestValidationRecordForInput:
    """Test ValidationRecord for user-created contributions."""

    def test_validation_record_with_source_input(self):
        """Test creating ValidationRecord with source='input'."""
        record = ValidationRecord(
            id="input_test123456",
            date=date.today().isoformat(),
            title="Test contribution",
            body="**Constat:**\nTest constat\n\n**Idées:**\nTest idées",
            category="economie",
            constat_factuel="Test constat",
            idees_ameliorations="Test idées",
            source="input",
            is_valid=True,
            violations=[],
            encouraged_aspects=[],
            confidence=1.0,
            reasoning="User-created contribution",
        )

        assert record.source == "input"
        assert record.is_valid is True
        assert record.confidence == 1.0
        assert record.id.startswith("input_")

    def test_validation_record_to_dict(self):
        """Test ValidationRecord serialization."""
        record = ValidationRecord(
            id="input_abc123",
            date="2026-01-29",
            title="Test",
            body="Test body",
            category="logement",
            source="input",
        )

        data = record.to_dict()

        assert data["id"] == "input_abc123"
        assert data["source"] == "input"
        assert data["category"] == "logement"

    def test_validation_record_from_dict(self):
        """Test ValidationRecord deserialization."""
        data = {
            "id": "input_xyz789",
            "date": "2026-01-29",
            "title": "From dict",
            "body": "Body content",
            "category": "culture",
            "source": "input",
            "is_valid": True,
            "confidence": 1.0,
        }

        record = ValidationRecord.from_dict(data)

        assert record.id == "input_xyz789"
        assert record.source == "input"
        assert record.is_valid is True

    def test_input_source_distinguishable_from_mockup(self):
        """Test that source='input' is different from other sources."""
        input_record = ValidationRecord(
            id="input_123",
            date="2026-01-29",
            title="User contribution",
            body="Body",
            source="input",
        )

        mock_record = ValidationRecord(
            id="mock_456",
            date="2026-01-29",
            title="Mock contribution",
            body="Body",
            source="mock",
        )

        derived_record = ValidationRecord(
            id="field_789",
            date="2026-01-29",
            title="Derived contribution",
            body="Body",
            source="derived",
        )

        assert input_record.source == "input"
        assert mock_record.source == "mock"
        assert derived_record.source == "derived"
        assert input_record.source != mock_record.source
        assert input_record.source != derived_record.source


class TestQuestionsViewHelpers:
    """Test helper functions from views module."""

    def test_draft_contribution_to_validation_record(self):
        """Test converting DraftContribution to ValidationRecord format."""
        draft = DraftContribution(
            constat_factuel="Le port manque de places de stationnement en été",
            idees_ameliorations="Créer un parking relais à l'entrée de la ville",
            category="economie",
            source_title="Voeux du maire 2026",
        )

        # Simulate what _save_contribution does
        body = (
            f"**Constat factuel:**\n{draft.constat_factuel}\n\n"
            f"**Idées d'améliorations:**\n{draft.idees_ameliorations}"
        )
        title = draft.constat_factuel[:80]

        record = ValidationRecord(
            id="input_test12345",
            date=date.today().isoformat(),
            title=title,
            body=body,
            category=draft.category,
            constat_factuel=draft.constat_factuel,
            idees_ameliorations=draft.idees_ameliorations,
            source="input",
            is_valid=True,
            confidence=1.0,
        )

        assert record.constat_factuel == draft.constat_factuel
        assert record.idees_ameliorations == draft.idees_ameliorations
        assert record.category == draft.category
        assert "**Constat factuel:**" in record.body
        assert "**Idées d'améliorations:**" in record.body


class TestOpikDatasetExport:
    """Test that input contributions export correctly for Opik."""

    def test_to_opik_item_format(self):
        """Test ValidationRecord.to_opik_item() for input source."""
        record = ValidationRecord(
            id="input_opik_test",
            date="2026-01-29",
            title="Test for Opik",
            body="Body content",
            category="ecologie",
            constat_factuel="Environmental observation",
            idees_ameliorations="Green solutions",
            source="input",
            is_valid=True,
            violations=[],
            encouraged_aspects=["Constructive"],
            confidence=1.0,
            reasoning="User-created via Questions assistant",
        )

        opik_item = record.to_opik_item()

        assert "input" in opik_item
        assert "expected_output" in opik_item
        assert "metadata" in opik_item

        # Check input fields
        assert opik_item["input"]["constat_factuel"] == "Environmental observation"
        assert opik_item["input"]["idees_ameliorations"] == "Green solutions"

        # Check expected output
        assert opik_item["expected_output"]["is_valid"] is True
        assert opik_item["expected_output"]["confidence"] == 1.0

        # Check metadata
        assert opik_item["metadata"]["source"] == "input"
        assert opik_item["metadata"]["id"] == "input_opik_test"
