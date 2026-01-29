# app/processors/workflows/__init__.py
"""
Workflow Processors

Orchestrate multi-step business processes with clear function ordering.

Available Workflows:
- AutoContributionWorkflow: 5-step citizen contribution creation with Forseti validation
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

__all__ = [
    # Workflow class
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
]
