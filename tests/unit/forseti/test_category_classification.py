# test_category_classification.py
"""
Unit tests for Category Classification Feature.

Maps to Opik experiment: forseti-category-accuracy
Metrics: CategoryAccuracyMetric, CategoryConfusionMatrix
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
import json


def run_async(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


# Valid categories from the charter
VALID_CATEGORIES = [
    "economie",
    "logement",
    "culture",
    "ecologie",
    "associations",
    "jeunesse",
    "alimentation-bien-etre-soins",
]


class TestCategoryClassificationFeature:
    """Test CategoryClassificationFeature in isolation."""

    @pytest.fixture
    def classification_feature(self):
        """Create CategoryClassificationFeature instance."""
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        """Mock LLM provider."""
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_feature_name(self, classification_feature):
        """Feature has correct name for registration."""
        assert classification_feature.name == "category_classification"

    def test_prompt_exists(self, classification_feature):
        """Feature has a prompt template."""
        assert classification_feature.prompt is not None


class TestCategoryEconomie:
    """Test economie category classification.

    Topics: business, port, tourism, commerce, employment
    """

    @pytest.fixture
    def classification_feature(self):
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_port_classified_as_economie(self, classification_feature, mock_provider):
        """Port-related contributions → economie."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "economie",
                    "reasoning": "Le port est un atout économique majeur.",
                    "confidence": 0.92,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Amélioration du port",
                body="Le port de pêche pourrait accueillir plus de chalutiers.",
            )
        )

        assert result.category == "economie"
        assert result.confidence > 0.85

    def test_tourism_classified_as_economie(self, classification_feature, mock_provider):
        """Tourism-related contributions → economie."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "economie",
                    "reasoning": "Le tourisme est un secteur économique.",
                    "confidence": 0.88,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Développer le tourisme",
                body="Audierne pourrait attirer plus de visiteurs avec des sentiers balisés.",
            )
        )

        assert result.category == "economie"

    def test_commerce_classified_as_economie(self, classification_feature, mock_provider):
        """Commerce-related contributions → economie."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "economie",
                    "reasoning": "Les commerces locaux relèvent de l'économie.",
                    "confidence": 0.90,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Soutenir les commerces",
                body="Il faudrait aider les petits commerces du centre-ville.",
            )
        )

        assert result.category == "economie"


class TestCategoryLogement:
    """Test logement category classification."""

    @pytest.fixture
    def classification_feature(self):
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_housing_classified_as_logement(self, classification_feature, mock_provider):
        """Housing-related contributions → logement."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "logement",
                    "reasoning": "La contribution concerne le logement.",
                    "confidence": 0.94,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Logements sociaux",
                body="Il manque des logements abordables pour les jeunes.",
            )
        )

        assert result.category == "logement"

    def test_urban_planning_classified_as_logement(
        self, classification_feature, mock_provider
    ):
        """Urban planning contributions → logement."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "logement",
                    "reasoning": "L'urbanisme relève du logement.",
                    "confidence": 0.86,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="PLU et construction",
                body="Les règles d'urbanisme devraient permettre plus de constructions.",
            )
        )

        assert result.category == "logement"


class TestCategoryCulture:
    """Test culture category classification."""

    @pytest.fixture
    def classification_feature(self):
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_heritage_classified_as_culture(self, classification_feature, mock_provider):
        """Heritage-related contributions → culture."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "culture",
                    "reasoning": "Le patrimoine relève de la culture.",
                    "confidence": 0.91,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Préserver le patrimoine",
                body="Les maisons de pêcheurs sont un patrimoine à protéger.",
            )
        )

        assert result.category == "culture"

    def test_festival_classified_as_culture(self, classification_feature, mock_provider):
        """Festival-related contributions → culture."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "culture",
                    "reasoning": "Les festivals sont des événements culturels.",
                    "confidence": 0.89,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Festival d'été",
                body="Organisons un festival de musique bretonne cet été.",
            )
        )

        assert result.category == "culture"


class TestCategoryEcologie:
    """Test ecologie category classification."""

    @pytest.fixture
    def classification_feature(self):
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_environment_classified_as_ecologie(
        self, classification_feature, mock_provider
    ):
        """Environment-related contributions → ecologie."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "ecologie",
                    "reasoning": "La protection de l'environnement relève de l'écologie.",
                    "confidence": 0.93,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Protéger la côte",
                body="Les dunes sont fragiles et doivent être protégées.",
            )
        )

        assert result.category == "ecologie"

    def test_energy_classified_as_ecologie(self, classification_feature, mock_provider):
        """Energy-related contributions → ecologie."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "ecologie",
                    "reasoning": "Les énergies renouvelables relèvent de l'écologie.",
                    "confidence": 0.87,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Panneaux solaires",
                body="Installer des panneaux solaires sur les bâtiments publics.",
            )
        )

        assert result.category == "ecologie"


class TestCategoryAssociations:
    """Test associations category classification."""

    @pytest.fixture
    def classification_feature(self):
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_club_classified_as_associations(self, classification_feature, mock_provider):
        """Club-related contributions → associations."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "associations",
                    "reasoning": "Les clubs sportifs sont des associations.",
                    "confidence": 0.90,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Club de voile",
                body="Le club de voile a besoin de locaux plus grands.",
            )
        )

        assert result.category == "associations"


class TestCategoryJeunesse:
    """Test jeunesse category classification."""

    @pytest.fixture
    def classification_feature(self):
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_school_classified_as_jeunesse(self, classification_feature, mock_provider):
        """School-related contributions → jeunesse."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "jeunesse",
                    "reasoning": "Les écoles concernent la jeunesse.",
                    "confidence": 0.92,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Cantine scolaire",
                body="Améliorer les repas de la cantine avec des produits locaux.",
            )
        )

        assert result.category == "jeunesse"


class TestCategoryAlimentationBienEtreSoins:
    """Test alimentation-bien-etre-soins category classification."""

    @pytest.fixture
    def classification_feature(self):
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_health_classified_correctly(self, classification_feature, mock_provider):
        """Health-related contributions → alimentation-bien-etre-soins."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "alimentation-bien-etre-soins",
                    "reasoning": "La santé relève de cette catégorie.",
                    "confidence": 0.88,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Médecin généraliste",
                body="Il nous faut un deuxième médecin généraliste dans la commune.",
            )
        )

        assert result.category == "alimentation-bien-etre-soins"

    def test_local_food_classified_correctly(self, classification_feature, mock_provider):
        """Local food contributions → alimentation-bien-etre-soins."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "alimentation-bien-etre-soins",
                    "reasoning": "L'alimentation locale relève de cette catégorie.",
                    "confidence": 0.85,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Marché local",
                body="Créer un marché de producteurs locaux chaque semaine.",
            )
        )

        assert result.category == "alimentation-bien-etre-soins"


class TestCategoryEdgeCases:
    """Test edge cases and category corrections."""

    @pytest.fixture
    def classification_feature(self):
        from app.agents.forseti.features import CategoryClassificationFeature

        return CategoryClassificationFeature()

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        provider.complete = AsyncMock()
        return provider

    def test_invalid_category_defaults_to_first(
        self, classification_feature, mock_provider
    ):
        """Invalid category from LLM defaults to first category."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "invalid_category",
                    "reasoning": "Test",
                    "confidence": 0.5,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Test",
                body="Test content",
            )
        )

        assert result.category in VALID_CATEGORIES

    def test_preserves_current_category_on_error(
        self, classification_feature, mock_provider
    ):
        """On error, preserves current category if provided."""
        mock_provider.complete.side_effect = Exception("API Error")

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Test",
                body="Test content",
                current_category="logement",
            )
        )

        assert result.category == "logement"

    def test_category_correction_from_existing(
        self, classification_feature, mock_provider
    ):
        """Can correct an existing incorrect category."""
        mock_provider.complete.return_value = MagicMock(
            content=json.dumps(
                {
                    "category": "ecologie",  # Corrected from economie
                    "reasoning": "Le sujet est environnemental, pas économique.",
                    "confidence": 0.82,
                }
            )
        )

        result = run_async(
            classification_feature.execute(
                provider=mock_provider,
                system_prompt="You are Forseti 461...",
                title="Protection des oiseaux",
                body="Les oiseaux migrateurs doivent être protégés.",
                current_category="economie",  # Incorrect
            )
        )

        assert result.category == "ecologie"


class TestCategoryConfusionMatrix:
    """Test cases for building category confusion matrix."""

    @pytest.fixture
    def confusion_cases(self):
        """Cases that are often confused between categories."""
        return [
            {
                "input": {
                    "title": "Tourisme vert",
                    "body": "Développer l'écotourisme pour protéger la nature.",
                },
                "likely_categories": ["economie", "ecologie"],
                "expected": "economie",
            },
            {
                "input": {
                    "title": "Cantine bio",
                    "body": "Proposer des repas bio à la cantine scolaire.",
                },
                "likely_categories": ["jeunesse", "alimentation-bien-etre-soins"],
                "expected": "jeunesse",
            },
        ]

    def test_confusion_cases_defined(self, confusion_cases):
        """Verify confusion test cases are properly defined."""
        for case in confusion_cases:
            assert "input" in case
            assert "likely_categories" in case
            assert "expected" in case
            assert len(case["likely_categories"]) >= 2
