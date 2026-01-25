"""
Wording Correction Feature

Suggests improvements to contribution wording for clarity and constructiveness.
"""

from app.providers import LLMProvider

from ..models import WordingResult
from ..prompts import WORDING_CORRECTION_PROMPT
from .base import FeatureBase


class WordingCorrectionFeature(FeatureBase):
    """
    Feature for improving contribution wording.

    Improvements include:
    - Clarity and readability
    - Grammar corrections
    - More constructive phrasing
    - Removing inflammatory language
    - Preserving original intent
    """

    @property
    def name(self) -> str:
        return "wording_correction"

    @property
    def prompt(self) -> str:
        return WORDING_CORRECTION_PROMPT

    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        title: str,
        body: str,
        **kwargs,
    ) -> WordingResult:
        """
        Suggest wording improvements for a contribution.

        Args:
            provider: LLM provider.
            system_prompt: Agent persona prompt.
            title: Contribution title.
            body: Contribution body.

        Returns:
            WordingResult with original and corrected text.
        """
        original = f"{title}\n\n{body}"

        user_prompt = self.format_prompt(title=title, body=body)

        try:
            data = await self._get_json_response(
                provider=provider,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.5,  # Slightly higher for creative corrections
            )

            return WordingResult(
                original=original,
                corrected=data.get("corrected", original),
                changes=data.get("changes", []),
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            return WordingResult(
                original=original,
                corrected=original,  # No changes on error
                changes=[],
                reasoning=f"Correction error: {e}",
            )
