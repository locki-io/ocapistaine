# test_charter_validation.py
"""
Unit tests for Charter Validation Feature.

Maps to Opik experiment: forseti-charter-accuracy
Metrics: CharterAccuracyMetric, ViolationDetectionMetric
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
import json


def run_async(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


class TestCharterValidationFeature:
    """Test CharterValidationFeature in isolation."""

    @pytest.fixture
    def charter_feature(self):
        """Create CharterValidationFeature instance."""
        from app.agents.forseti.features import CharterValidationFeature

        return CharterValidationFeature()

    @pytest.fixture
    def mock_provider(self):
        """Mock LLM provider."""
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_feature_name(self, charter_feature):
        """Feature has correct name for registration."""
        assert charter_feature.name == "charter_validation"

    def test_prompt_exists(self, charter_feature):
        """Feature has a prompt template."""
        assert charter_feature.prompt is not None
        assert len(charter_feature.prompt) > 0


class TestCharterValidationCompliant:
    """Test cases for compliant contributions.

    These map to Opik dataset items with expected_output.is_valid=True
    """

    @pytest.fixture
    def charter_feature(self):
        from app.agents.forseti.features import CharterValidationFeature

        return CharterValidationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_concrete_proposal_is_valid(self, charter_feature, mock_provider):
        """Concrete proposals with arguments are valid."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": True,
                    "violations": [],
                    "encouraged_aspects": ["Proposition concrète et argumentée"],
                    "reasoning": "La contribution propose des améliorations concrètes.",
                    "confidence": 0.92,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="[economie] Amélioration du port",
                body="Je propose de moderniser les pontons du port pour accueillir plus de plaisanciers.",
            )
        )

        assert result.is_valid is True
        assert len(result.violations) == 0
        assert len(result.encouraged_aspects) > 0
        assert result.confidence > 0.8

    def test_constructive_criticism_is_valid(self, charter_feature, mock_provider):
        """Constructive criticism with suggestions is valid."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": True,
                    "violations": [],
                    "encouraged_aspects": ["Critique constructive"],
                    "reasoning": "La critique est accompagnée de suggestions.",
                    "confidence": 0.88,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="[logement] Problème de stationnement",
                body="Le stationnement est difficile en été. Pourrait-on créer un parking relais?",
            )
        )

        assert result.is_valid is True

    def test_question_for_clarification_is_valid(self, charter_feature, mock_provider):
        """Questions requesting clarification are valid."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": True,
                    "violations": [],
                    "encouraged_aspects": ["Demande de clarification"],
                    "reasoning": "Question légitime sur un projet municipal.",
                    "confidence": 0.85,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Question sur le budget",
                body="Quel est le budget prévu pour la rénovation de la salle des fêtes?",
            )
        )

        assert result.is_valid is True


class TestCharterValidationNonCompliant:
    """Test cases for non-compliant contributions.

    These map to Opik dataset items with expected_output.is_valid=False
    """

    @pytest.fixture
    def charter_feature(self):
        from app.agents.forseti.features import CharterValidationFeature

        return CharterValidationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_personal_attack_is_invalid(self, charter_feature, mock_provider):
        """Personal attacks are rejected."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": False,
                    "violations": ["Attaque personnelle"],
                    "encouraged_aspects": [],
                    "reasoning": "La contribution contient une attaque personnelle.",
                    "confidence": 0.95,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Le maire est incompétent",
                body="Le maire ne fait rien, c'est un incapable qui devrait démissionner.",
            )
        )

        assert result.is_valid is False
        assert "Attaque personnelle" in result.violations[0]
        assert result.confidence > 0.9

    def test_spam_advertising_is_invalid(self, charter_feature, mock_provider):
        """Spam and advertising are rejected."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": False,
                    "violations": ["Spam ou publicité"],
                    "encouraged_aspects": [],
                    "reasoning": "La contribution est une publicité déguisée.",
                    "confidence": 0.90,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Super offre immobilière",
                body="Achetez votre maison à Audierne! Contactez-moi au 06.XX.XX.XX.XX",
            )
        )

        assert result.is_valid is False
        assert any("Spam" in v or "publicité" in v for v in result.violations)

    def test_off_topic_is_invalid(self, charter_feature, mock_provider):
        """Off-topic content (not about Audierne) is rejected."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": False,
                    "violations": ["Hors sujet - sans rapport avec Audierne-Esquibien"],
                    "encouraged_aspects": [],
                    "reasoning": "La contribution ne concerne pas Audierne.",
                    "confidence": 0.88,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Météo à Paris",
                body="Il fait beau à Paris aujourd'hui, j'adore cette ville!",
            )
        )

        assert result.is_valid is False

    def test_discriminatory_content_is_invalid(self, charter_feature, mock_provider):
        """Discriminatory remarks are rejected."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": False,
                    "violations": ["Propos discriminatoires"],
                    "encouraged_aspects": [],
                    "reasoning": "La contribution contient des propos discriminatoires.",
                    "confidence": 0.97,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Trop d'étrangers",
                body="Il y a trop de [group] dans notre ville, il faut les expulser.",
            )
        )

        assert result.is_valid is False
        assert result.confidence > 0.95


class TestCharterValidationEdgeCases:
    """Test edge cases and error handling.

    These help calibrate confidence thresholds.
    """

    @pytest.fixture
    def charter_feature(self):
        from app.agents.forseti.features import CharterValidationFeature

        return CharterValidationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_empty_body_low_confidence(self, charter_feature, mock_provider):
        """Empty or minimal content should have low confidence."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": True,
                    "violations": [],
                    "encouraged_aspects": [],
                    "reasoning": "Contenu insuffisant pour évaluation.",
                    "confidence": 0.3,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Test",
                body="",
            )
        )

        assert result.confidence < 0.5

    def test_ambiguous_content_medium_confidence(self, charter_feature, mock_provider):
        """Ambiguous content should have medium confidence."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "is_valid": True,
                    "violations": [],
                    "encouraged_aspects": [],
                    "reasoning": "Le contenu est ambigu.",
                    "confidence": 0.6,
                }
            )
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="À propos",
                body="Je ne suis pas content de la situation actuelle.",
            )
        )

        assert 0.5 <= result.confidence <= 0.7

    def test_provider_error_fails_open(self, charter_feature, mock_provider):
        """Provider errors should fail open (is_valid=True)."""
        mock_provider.complete.side_effect = Exception("API Error")

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Test",
                body="Test content",
            )
        )

        # Fail open - don't reject on error
        assert result.is_valid is True
        assert result.confidence == 0.5
        assert "error" in result.reasoning.lower()

    def test_malformed_json_fails_open(self, charter_feature, mock_provider):
        """Malformed JSON response should fail open."""
        mock_provider.complete.return_value = MagicMock(
            content="This is not valid JSON"
        )

        result = run_async(
            charter_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Test",
                body="Test content",
            )
        )

        assert result.is_valid is True
        assert result.confidence == 0.5


class TestCharterValidationOpikMapping:
    """Test cases that directly map to Opik dataset items.

    Use these as reference for creating Opik datasets.
    """

    @pytest.fixture
    def opik_valid_item(self):
        """Sample Opik item for valid contribution."""
        return {
            "input": {
                "title": "[economie] Proposition pour le port",
                "body": "Je propose d'améliorer les infrastructures portuaires pour attirer plus de touristes.",
            },
            "expected_output": {
                "is_valid": True,
                "violations": [],
                "confidence_min": 0.8,
            },
            "metadata": {"source": "test", "category": "economie"},
        }

    @pytest.fixture
    def opik_invalid_item(self):
        """Sample Opik item for invalid contribution."""
        return {
            "input": {
                "title": "Maire incompétent",
                "body": "Le maire est un idiot qui ne comprend rien.",
            },
            "expected_output": {
                "is_valid": False,
                "violations": ["Attaque personnelle"],
                "confidence_min": 0.85,
            },
            "metadata": {"source": "test", "violation_type": "personal_attack"},
        }

    def test_opik_item_structure_valid(self, opik_valid_item):
        """Verify valid Opik item has correct structure."""
        assert "input" in opik_valid_item
        assert "expected_output" in opik_valid_item
        assert "title" in opik_valid_item["input"]
        assert "body" in opik_valid_item["input"]
        assert "is_valid" in opik_valid_item["expected_output"]

    def test_opik_item_structure_invalid(self, opik_invalid_item):
        """Verify invalid Opik item has correct structure."""
        assert opik_invalid_item["expected_output"]["is_valid"] is False
        assert len(opik_invalid_item["expected_output"]["violations"]) > 0
