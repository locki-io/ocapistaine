# app/processors/__init__.py
"""
Business Logic Processors (Apache 2.0 Licensed)

Processors transform and process data without implementing core business logic.
They are stateless and reusable across different agents and services.

Available Processors:
- MockupProcessor: Charter validation testing workflow
- AutoContributionWorkflow: 5-step citizen contribution creation
- (Planned) EmbeddingsProcessor: Vector embedding generation
- (Planned) DocumentParser: PDF/HTML text extraction
- (Planned) ResponseFormatter: Format answers with sources
"""

from app.processors.mockup_processor import (
    MockupProcessor,
    MockupWorkflowConfig,
    MockupWorkflowResult,
    ExperimentResult,
    CharterAccuracyMetric,
    ViolationDetectionMetric,
    ConfidenceCalibrationMetric,
    run_mockup_workflow,
)

from app.processors.workflows import (
    AutoContributionWorkflow,
    AutoContributionConfig,
    AutoContributionResult,
    DraftContribution,
    step_1_load_sources,
    step_2_select_category,
    step_3_generate_draft,
    step_5_validate_and_save,
    run_forseti_validation,
    generate_draft_sync,
)

__all__ = [
    # Mockup Processor
    "MockupProcessor",
    "MockupWorkflowConfig",
    "MockupWorkflowResult",
    "run_mockup_workflow",
    # Experiment Support
    "ExperimentResult",
    "CharterAccuracyMetric",
    "ViolationDetectionMetric",
    "ConfidenceCalibrationMetric",
    # Auto-Contribution Workflow
    "AutoContributionWorkflow",
    "AutoContributionConfig",
    "AutoContributionResult",
    "DraftContribution",
    "step_1_load_sources",
    "step_2_select_category",
    "step_3_generate_draft",
    "step_5_validate_and_save",
    "run_forseti_validation",
    "generate_draft_sync",
]
