# app/mockup/__init__.py
"""
OCapistaine - Contribution Mockup System

Generate and manage mock contributions for batch testing Forseti validation.

Mutation strategies:
- Levenshtein distance: Character-level mutations (orthographic errors, typos)
- LLM (Ollama/Mistral): Semantic mutations (paraphrasing, subtle violations)

Storage:
- Redis: contribution_mockup:forseti461:charter:{date}:{id}
- Opik datasets for prompt optimization
"""

from app.mockup.generator import (
    ContributionGenerator,
    MockContribution,
    generate_variations,
    generate_variations_async,
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

from app.mockup.llm_mutations import (
    LLMMutator,
    MutationType,
    MutationResult,
    mutate_with_llm,
    generate_llm_variations,
    check_ollama_available,
)

from app.mockup.field_input import (
    FieldInputGenerator,
    FieldInputResult,
    ExtractedTheme,
    list_audierne_docs,
    read_markdown_input,
    process_field_input_sync,
    load_category_themes,
    RECOMMENDED_MODELS,
    ProviderType,
)

# Import categories from Forseti (single source of truth)
from app.agents.forseti import CATEGORIES, CATEGORY_DESCRIPTIONS

__all__ = [
    # Generator
    "ContributionGenerator",
    "MockContribution",
    "generate_variations",
    "generate_variations_async",
    "load_contributions",
    "save_contributions",
    # Levenshtein (text-based)
    "levenshtein_distance",
    "levenshtein_ratio",
    "apply_distance",
    # LLM Mutations
    "LLMMutator",
    "MutationType",
    "MutationResult",
    "mutate_with_llm",
    "generate_llm_variations",
    "check_ollama_available",
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
    # Field Input
    "FieldInputGenerator",
    "FieldInputResult",
    "ExtractedTheme",
    "list_audierne_docs",
    "read_markdown_input",
    "process_field_input_sync",
    "load_category_themes",
    "RECOMMENDED_MODELS",
    "ProviderType",
    # Categories (from Forseti - single source of truth)
    "CATEGORIES",
    "CATEGORY_DESCRIPTIONS",
]
