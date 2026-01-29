# app/auto_contribution/__init__.py
"""
Auto-Contribution Module - Citizen Contribution Creation Assistant

Provides a 5-step Streamlit UI for creating charter-compliant contributions:
1. Select inspiration source (documents or paste text)
2. Choose category
3. Generate AI draft
4. Edit contribution
5. Validate with Forseti 461 and save

The business logic is in app/processors/workflows/workflow_autocontribution.py
This module provides the Streamlit UI views.
"""

from .views import autocontribution_view

# Re-export workflow components for convenience
from app.processors.workflows.workflow_autocontribution import (
    AutoContributionWorkflow,
    AutoContributionConfig,
    AutoContributionResult,
    DraftContribution,
    CATEGORY_DESCRIPTIONS,
)

__all__ = [
    # UI View
    "autocontribution_view",
    # Workflow components
    "AutoContributionWorkflow",
    "AutoContributionConfig",
    "AutoContributionResult",
    "DraftContribution",
    "CATEGORY_DESCRIPTIONS",
]
