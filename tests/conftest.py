# conftest.py
"""
Shared pytest fixtures for OCapistaine tests.

Provides mocked providers, sample data, and common test utilities.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime


# === Pytest Markers ===

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "slow: marks tests as slow running")
    config.addinivalue_line("markers", "opik: marks tests requiring Opik connection")


# === Mock LLM Providers ===

@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider that returns controlled responses."""
    provider = MagicMock()
    provider.generate = AsyncMock(return_value="mocked response")
    provider.model = "mock-model"
    return provider


@pytest.fixture
def mock_forseti_valid_response():
    """Mock Forseti response for valid contribution."""
    return """{
        "is_valid": true,
        "category": "economie",
        "violations": [],
        "encouraged_aspects": ["Proposition constructive", "Budget considéré"],
        "reasoning": "La contribution propose des améliorations concrètes.",
        "confidence": 0.85
    }"""


@pytest.fixture
def mock_forseti_invalid_response():
    """Mock Forseti response for invalid contribution."""
    return """{
        "is_valid": false,
        "category": null,
        "violations": ["Attaque personnelle détectée", "Pas de proposition constructive"],
        "encouraged_aspects": [],
        "reasoning": "La contribution contient des critiques sans propositions.",
        "confidence": 0.78
    }"""


# === Mock N8N Responses ===

@pytest.fixture
def mock_n8n_label_added():
    """Mock N8N response when label is added."""
    return [{
        "success": True,
        "issueNumber": 64,
        "isValid": True,
        "new_category": "logement",
        "category_labels": ["conforme charte"],
        "new_title": "",
        "should_replace_label": True,
        "reason": "Label added"
    }]


@pytest.fixture
def mock_n8n_already_labeled():
    """Mock N8N response when issue already has label."""
    return [{
        "success": False,
        "issueNumber": 64,
        "isValid": True,
        "new_category": "logement",
        "category_labels": ["conforme charte"],
        "new_title": "",
        "should_replace_label": False,
        "reason": "Already has conforme charte label"
    }]


@pytest.fixture
def mock_n8n_not_assigned():
    """Mock N8N response when task not assigned to Forseti."""
    return [{
        "success": False,
        "issueNumber": 64,
        "isValid": True,
        "new_category": "logement",
        "category_labels": [],
        "new_title": "",
        "should_replace_label": False,
        "reason": "task not assigned to forseti461"
    }]


# === Mock Redis ===

@pytest.fixture
def mock_redis():
    """Mock Redis client for storage tests."""
    redis = MagicMock()
    redis.hset = MagicMock(return_value=True)
    redis.hget = MagicMock(return_value=None)
    redis.hgetall = MagicMock(return_value={})
    redis.keys = MagicMock(return_value=[])
    redis.pipeline = MagicMock(return_value=MagicMock(
        execute=MagicMock(return_value=[])
    ))
    return redis


# === Sample Contributions ===

@pytest.fixture
def sample_contribution_valid():
    """Sample valid contribution for testing."""
    return {
        "title": "[economie] Proposition pour le port",
        "body": """Submitted on Lundi, janvier 20, 2026 - 10:30
Soumis par un utilisateur anonyme

category: economie
# Constat factuel:
Le port d'Audierne manque d'infrastructures modernes pour accueillir les plaisanciers.

# Vos idées d'améliorations:
Je propose de moderniser les pontons et d'ajouter des bornes électriques.
Cela permettrait d'attirer plus de visiteurs et de dynamiser l'économie locale.""",
        "category": "economie",
        "issue_id": 64
    }


@pytest.fixture
def sample_contribution_invalid():
    """Sample invalid contribution (personal attack)."""
    return {
        "title": "Le maire est incompétent",
        "body": """Le maire ne fait rien pour la ville.
Il devrait démissionner immédiatement.""",
        "category": None,
        "issue_id": 65
    }


@pytest.fixture
def sample_contribution_framaforms():
    """Sample contribution from Framaforms."""
    return {
        "constat_factuel": "Les trottoirs de la rue principale sont en mauvais état.",
        "idees_ameliorations": "Refaire les trottoirs avec des matériaux adaptés aux PMR.",
        "category": "logement",
        "source": "framaforms"
    }


# === ValidationRecord Fixtures ===

@pytest.fixture
def sample_validation_record():
    """Sample ValidationRecord for testing."""
    from app.mockup.storage import ValidationRecord
    return ValidationRecord(
        id="test-123",
        constat_factuel="Le port nécessite des rénovations",
        idees_ameliorations="Moderniser les quais et ajouter des services",
        category="economie",
        is_valid=True,
        violations=[],
        encouraged_aspects=["Proposition concrète", "Budget considéré"],
        reasoning="Contribution constructive avec des propositions claires.",
        confidence=0.9,
        source="test",
        created_at=datetime.now().isoformat()
    )


@pytest.fixture
def sample_validation_record_invalid():
    """Sample invalid ValidationRecord."""
    from app.mockup.storage import ValidationRecord
    return ValidationRecord(
        id="test-456",
        constat_factuel="Critique sans fondement",
        idees_ameliorations="",
        category=None,
        is_valid=False,
        violations=["Pas de proposition constructive", "Ton non respectueux"],
        encouraged_aspects=[],
        reasoning="La contribution ne respecte pas la charte.",
        confidence=0.75,
        source="test",
        created_at=datetime.now().isoformat()
    )


# === DraftContribution Fixtures ===

@pytest.fixture
def sample_draft_contribution():
    """Sample DraftContribution for testing."""
    from app.agents.contribution_assistant import DraftContribution
    return DraftContribution(
        title="[economie] Proposition pour le commerce local",
        constat_factuel="Les commerces du centre-ville ferment un par un.",
        idees_ameliorations="Créer une zone piétonne et soutenir les commerçants locaux.",
        category="economie",
        source_title="Contribution citoyenne",
        source_url=""
    )


# === GitHub Issue Fixtures ===

@pytest.fixture
def sample_github_issue():
    """Sample GitHub issue data (as returned by N8N)."""
    return {
        "number": 64,
        "title": "[logement] contribution du Jeudi, janvier 15, 2026 - 09:29",
        "body": """Submitted on Jeudi, janvier 15, 2026 - 09:29
category: logement
# Constat factuel:
construction des maisons au style toit plat
# Vos idées d'améliorations:
Ne peut-on pas envisager des contraintes architecturales...""",
        "state": "open",
        "labels": [
            {"name": "conforme charte", "color": "16e05f"},
            {"name": "economie", "color": "b90457"}
        ],
        "html_url": "https://github.com/audierne2026/participons/issues/64",
        "user": {"login": "jnschilling"}
    }


# === Opik Fixtures ===

@pytest.fixture
def sample_opik_item():
    """Sample item in Opik dataset format."""
    return {
        "input": {
            "constat_factuel": "Le port nécessite des rénovations",
            "idees_ameliorations": "Moderniser les quais",
            "category": "economie"
        },
        "expected_output": {
            "is_valid": True,
            "violations": [],
            "encouraged_aspects": ["Proposition concrète"],
            "confidence": 0.9
        },
        "metadata": {
            "source": "test",
            "id": "test-123",
            "created_at": "2026-01-30T10:00:00"
        }
    }


# === HTTP Response Mocks ===

@pytest.fixture
def mock_http_response_ok():
    """Mock successful HTTP response."""
    response = MagicMock()
    response.ok = True
    response.status_code = 200
    response.json = MagicMock(return_value={})
    return response


@pytest.fixture
def mock_http_response_error():
    """Mock failed HTTP response."""
    response = MagicMock()
    response.ok = False
    response.status_code = 500
    response.text = "Internal Server Error"
    return response


# === Test Utilities ===

@pytest.fixture
def temp_redis_key():
    """Generate a temporary Redis key for testing."""
    import uuid
    return f"test:{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_redis(mock_redis, temp_redis_key):
    """Cleanup Redis after test."""
    yield temp_redis_key
    # Cleanup would happen here with real Redis
    pass
