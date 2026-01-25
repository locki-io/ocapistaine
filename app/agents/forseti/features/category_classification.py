"""
Category Classification Feature

Classifies citizen contributions into one of 7 predefined categories.
"""

from app.providers import LLMProvider

from ..models import ClassificationResult, CATEGORIES
from ..prompts import CATEGORY_CLASSIFICATION_PROMPT
from .base import FeatureBase


class CategoryClassificationFeature(FeatureBase):
    """
    Feature for classifying contributions into categories.

    Categories:
    - economie: business, port, tourism
    - logement: housing
    - culture: heritage, events
    - ecologie: environment
    - associations: organizations
    - jeunesse: youth, schools
    - alimentation-bien-etre-soins: food, health
    """

    @property
    def name(self) -> str:
        return "category_classification"

    @property
    def prompt(self) -> str:
        return CATEGORY_CLASSIFICATION_PROMPT

    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        title: str,
        body: str,
        current_category: str | None = None,
        **kwargs,
    ) -> ClassificationResult:
        """
        Classify a contribution into one of the 7 categories.

        Args:
            provider: LLM provider.
            system_prompt: Agent persona prompt.
            title: Contribution title.
            body: Contribution body.
            current_category: Optional existing category for reference.

        Returns:
            ClassificationResult with assigned category.
        """
        current_category_line = (
            f"CURRENT CATEGORY: {current_category}"
            if current_category
            else ""
        )

        user_prompt = self.format_prompt(
            title=title,
            body=body,
            current_category_line=current_category_line,
        )

        try:
            data = await self._get_json_response(
                provider=provider,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )

            category = data.get("category", CATEGORIES[0])
            # Validate category is in allowed list
            if category not in CATEGORIES:
                category = CATEGORIES[0]

            return ClassificationResult(
                category=category,
                reasoning=data.get("reasoning", ""),
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception as e:
            return ClassificationResult(
                category=current_category or CATEGORIES[0],
                reasoning=f"Classification error: {e}",
                confidence=0.5,
            )
