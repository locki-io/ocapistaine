# app/processors/workflows/__init__.py
"""
Workflow Processors

Orchestrate multi-step business processes with clear function ordering.

Available Workflows:
- AutoContributionWorkflow: 5-step citizen contribution creation with Forseti validation
- workflow_dataset: Create Opik datasets from spans/records for optimization
- workflow_experiment: Run prompt optimization experiments
"""

from .workflow_autocontribution import (
    AutoContributionWorkflow,
    AutoContributionConfig,
    AutoContributionResult,
    DraftContribution,
    # Step functions
    step_1_load_sources,
    step_2_select_category,
    step_3_generate_draft,
    step_4_edit_contribution,
    step_5_validate_and_save,
    # Utilities
    run_forseti_validation,
    generate_draft_sync,
)

from .workflow_dataset import (
    create_dataset_from_spans,
    create_dataset_from_storage,
    list_datasets,
    migrate_dataset_category_field,
    migrate_all_datasets_category_field,
)

from .workflow_experiment import (
    OpikExperimentConfig,
    run_opik_experiment,
    list_experiment_types,
    list_available_metrics,
    get_experiment_filters,
    create_charter_compliance_metric,
    create_confidence_metric,
    # Dataset Assembly
    assemble_optimization_dataset,
    list_available_datasets,
)

__all__ = [
    # AutoContribution Workflow
    "AutoContributionWorkflow",
    "AutoContributionConfig",
    "AutoContributionResult",
    "DraftContribution",
    # Step functions
    "step_1_load_sources",
    "step_2_select_category",
    "step_3_generate_draft",
    "step_4_edit_contribution",
    "step_5_validate_and_save",
    # Utilities
    "run_forseti_validation",
    "generate_draft_sync",
    # Dataset Workflow
    "create_dataset_from_spans",
    "create_dataset_from_storage",
    "list_datasets",
    "migrate_dataset_category_field",
    "migrate_all_datasets_category_field",
    # Experiment Workflow (Opik native)
    "OpikExperimentConfig",
    "run_opik_experiment",
    "list_experiment_types",
    "list_available_metrics",
    "get_experiment_filters",
    "create_charter_compliance_metric",
    "create_confidence_metric",
    # Dataset Assembly
    "assemble_optimization_dataset",
    "list_available_datasets",
]
