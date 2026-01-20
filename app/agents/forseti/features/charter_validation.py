"""
Charter Validation Feature

Validates citizen contributions against the charter rules.
"""

from app.providers import LLMProvider
from app.agents.tracing import trace_feature

from ..models import ValidationResult
from ..prompts import CHARTER_VALIDATION_PROMPT
from .base import FeatureBase


class CharterValidationFeature(FeatureBase):
    """
    Feature for validating contributions against the charter.

    Checks for:
    - Personal attacks or discrimination
    - Spam or advertising
    - Off-topic content (unrelated to Audierne-Esquibien)
    - False information

    Identifies positive aspects:
    - Concrete proposals
    - Constructive criticism
    - Questions and clarifications
    - Shared expertise
    - Improvement suggestions
    """

    @property
    def name(self) -> str:
        return "charter_validation"

    @property
    def prompt(self) -> str:
        return CHARTER_VALIDATION_PROMPT

    @trace_feature("charter_validation")
    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        title: str,
        body: str,
        **kwargs,
    ) -> ValidationResult:
        """
        Validate a contribution against the charter.

        Args:
            provider: LLM provider.
            system_prompt: Agent persona prompt.
            title: Contribution title.
            body: Contribution body.

        Returns:
            ValidationResult with validation details.
        """
        user_prompt = self.format_prompt(title=title, body=body)

        try:
            data = await self._get_json_response(
                provider=provider,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )

            return ValidationResult(
                is_valid=data.get("is_valid", True),
                violations=data.get("violations", []),
                encouraged_aspects=data.get("encouraged_aspects", []),
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception as e:
            return ValidationResult(
                is_valid=True,  # Fail open
                violations=[],
                encouraged_aspects=[],
                reasoning=f"Validation error: {e}",
                confidence=0.5,
            )
