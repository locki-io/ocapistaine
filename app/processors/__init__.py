# app/processors/__init__.py
"""
Business Logic Processors (Apache 2.0 Licensed)

Processors transform and process data without implementing core business logic.
They are stateless and reusable across different agents and services.

Available Processors:
- MockupProcessor: Charter validation testing workflow
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
]
