# app/mockup/__init__.py
"""
OCapistaine - Contribution Mockup System

Generate and manage mock contributions for batch testing Forseti validation.
Uses Levenshtein distance to create progressive variations from valid to invalid.

Storage:
- Redis: contribution_mockup:forseti461:charter:{date}:{id}
- Opik datasets for prompt optimization
"""

from app.mockup.generator import (
    ContributionGenerator,
    MockContribution,
    generate_variations,
    load_contributions,
    save_contributions,
)

from app.mockup.levenshtein import (
    levenshtein_distance,
    levenshtein_ratio,
    apply_distance,
)

from app.mockup.storage import (
    ValidationRecord,
    MockupStorage,
    MockupKeys,
    get_storage,
)

from app.mockup.dataset import (
    DatasetManager,
    get_dataset_manager,
    create_optimization_dataset,
    DATASET_TRAINING,
    DATASET_VALIDATION,
    DATASET_TEST,
)

__all__ = [
    # Generator
    "ContributionGenerator",
    "MockContribution",
    "generate_variations",
    "load_contributions",
    "save_contributions",
    # Levenshtein
    "levenshtein_distance",
    "levenshtein_ratio",
    "apply_distance",
    # Storage
    "ValidationRecord",
    "MockupStorage",
    "MockupKeys",
    "get_storage",
    # Dataset
    "DatasetManager",
    "get_dataset_manager",
    "create_optimization_dataset",
    "DATASET_TRAINING",
    "DATASET_VALIDATION",
    "DATASET_TEST",
]
