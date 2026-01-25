"""
Forseti Agent

The impartial guardian of truth and the contribution charter.
"""

import argparse
import asyncio
import json

from app.providers import LLMProvider
from app.agents.base import BaseAgent
from app.agents.tracing import AgentTracer, get_tracer

from .models import (
    FullValidationResult,
    ValidationResult,
    ClassificationResult,
    WordingResult,
    BatchItem,
    BatchResult,
    CATEGORIES,
)
from .prompts import PERSONA_PROMPT, BATCH_VALIDATION_PROMPT
from .features import (
    CharterValidationFeature,
    CategoryClassificationFeature,
    WordingCorrectionFeature,
)


class ForsetiAgent(BaseAgent):
    """
    Forseti 461 - Charter validation agent for Audierne2026.

    Features:
    - Charter validation: Check contributions against charter rules
    - Category classification: Assign contributions to categories
    - Wording correction: Suggest improvements (optional)

    Example:
        agent = ForsetiAgent()
        result = await agent.validate(title="...", body="...")
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        provider_name: str | None = None,
        enable_wording: bool = False,
        tracer: AgentTracer | None = None,
    ):
        """
        Initialize Forseti agent.

        Args:
            provider: Optional LLM provider instance.
            provider_name: Optional provider name ("gemini", "claude", etc.).
            enable_wording: If True, enable wording correction feature.
            tracer: Optional custom tracer (uses global tracer if None).
        """
        super().__init__(provider=provider, provider_name=provider_name)

        # Register core features
        self.register_feature(CharterValidationFeature())
        self.register_feature(CategoryClassificationFeature())

        # Optional features
        if enable_wording:
            self.register_feature(WordingCorrectionFeature())

        # Tracer
        self._tracer = tracer or get_tracer()

    @property
    def persona_prompt(self) -> str:
        return PERSONA_PROMPT

    async def validate(
        self,
        title: str,
        body: str,
        category: str | None = None,
    ) -> FullValidationResult:
        """
        Validate a contribution (charter + classification).

        Args:
            title: Contribution title.
            body: Contribution body.
            category: Optional existing category.

        Returns:
            FullValidationResult with validation and classification.
        """
        # Start a trace for the full validation with spans for each step
        with self._tracer.start_trace(
            name="forseti_validate",
            input={"title": title, "body": body, "category": category},
            tags=["forseti", "validation"],
        ) as trace:
            # Step 1: Charter validation
            with self._tracer.span(
                name="charter_validation",
                input={"title": title, "body": body},
                span_type="llm",
            ) as charter_span:
                validation: ValidationResult = await self.execute_feature(
                    "charter_validation",
                    title=title,
                    body=body,
                )
                charter_span.update(
                    output=validation.model_dump(),
                    metadata={"confidence": validation.confidence},
                )

            # Step 2: Category classification
            with self._tracer.span(
                name="category_classification",
                input={"title": title, "body": body, "current_category": category},
                span_type="llm",
            ) as category_span:
                classification: ClassificationResult = await self.execute_feature(
                    "category_classification",
                    title=title,
                    body=body,
                    current_category=category,
                )
                category_span.update(
                    output=classification.model_dump(),
                    metadata={"confidence": classification.confidence},
                )

            # Build result
            result = FullValidationResult(
                is_valid=validation.is_valid,
                category=classification.category,
                original_category=category,
                violations=validation.violations,
                encouraged_aspects=validation.encouraged_aspects,
                reasoning=(
                    f"Charter: {validation.reasoning} | "
                    f"Category: {classification.reasoning}"
                ),
                confidence=min(validation.confidence, classification.confidence),
            )

            # Update trace with final output
            if trace:
                trace.update(
                    output=result.model_dump(),
                    metadata={
                        "is_valid": result.is_valid,
                        "category": result.category,
                        "confidence": result.confidence,
                    },
                )

        return result

    async def validate_charter(
        self,
        title: str,
        body: str,
    ) -> ValidationResult:
        """
        Validate charter compliance only.

        Args:
            title: Contribution title.
            body: Contribution body.

        Returns:
            ValidationResult with validation details.
        """
        return await self.execute_feature(
            "charter_validation",
            title=title,
            body=body,
        )

    async def classify_category(
        self,
        title: str,
        body: str,
        current_category: str | None = None,
    ) -> ClassificationResult:
        """
        Classify category only.

        Args:
            title: Contribution title.
            body: Contribution body.
            current_category: Optional existing category.

        Returns:
            ClassificationResult with assigned category.
        """
        return await self.execute_feature(
            "category_classification",
            title=title,
            body=body,
            current_category=current_category,
        )

    async def correct_wording(
        self,
        title: str,
        body: str,
    ) -> WordingResult:
        """
        Suggest wording improvements.

        Args:
            title: Contribution title.
            body: Contribution body.

        Returns:
            WordingResult with corrections.

        Raises:
            KeyError: If wording correction feature is not enabled.
        """
        return await self.execute_feature(
            "wording_correction",
            title=title,
            body=body,
        )

    async def validate_batch(
        self,
        items: list[BatchItem],
    ) -> list[BatchResult]:
        """
        Validate multiple contributions in a single call.

        Args:
            items: List of BatchItem to validate.

        Returns:
            List of BatchResult, one per input item.
        """
        items_json = json.dumps(
            [item.model_dump() for item in items],
            ensure_ascii=False,
        )

        prompt = BATCH_VALIDATION_PROMPT.format(items_json=items_json)

        try:
            from app.providers import Message

            messages = [
                Message(role="system", content=self.persona_prompt),
                Message(role="user", content=prompt),
            ]

            response = await self._provider.complete(
                messages=messages,
                temperature=0.3,
                json_mode=True,
            )

            data = json.loads(response.content)
            results = data.get("results", [])

            return [
                BatchResult(
                    id=r.get("id", ""),
                    is_valid=r.get("is_valid", True),
                    violations=r.get("violations", []),
                    encouraged_aspects=r.get("encouraged_aspects", []),
                    category=r.get("category", CATEGORIES[0]),
                    reasoning=r.get("reasoning", ""),
                    confidence=float(r.get("confidence", 0.5)),
                )
                for r in results
            ]
        except Exception as e:
            # Return safe defaults on error
            return [
                BatchResult(
                    id=item.id,
                    is_valid=True,
                    violations=[],
                    encouraged_aspects=[],
                    category=item.category or CATEGORIES[0],
                    reasoning=f"Batch error: {e}",
                    confidence=0.5,
                )
                for item in items
            ]


# =============================================================================
# CLI Support
# =============================================================================


async def main_async():
    """Async CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Forseti 461 - Charter Validation Agent"
    )
    parser.add_argument("--title", required=True, help="Contribution title")
    parser.add_argument("--body", required=True, help="Contribution body")
    parser.add_argument("--category", help="Optional existing category")
    parser.add_argument(
        "--provider",
        choices=["gemini", "claude", "mistral", "ollama"],
        help="LLM provider to use",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON format",
    )
    args = parser.parse_args()

    agent = ForsetiAgent(provider_name=args.provider)
    result = await agent.validate(
        title=args.title,
        body=args.body,
        category=args.category,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print("FORSETI 461 - VALIDATION RESULT")
        print(f"{'='*60}")
        print(f"Valid: {result.is_valid}")
        if result.violations:
            print(f"Violations: {', '.join(result.violations)}")
        if result.encouraged_aspects:
            print(f"Encouraged: {', '.join(result.encouraged_aspects)}")
        cat_info = result.category
        if result.original_category and result.original_category != result.category:
            cat_info += f" (was {result.original_category})"
        print(f"Category: {cat_info}")
        print(f"Reasoning: {result.reasoning}")
        print(f"Confidence: {result.confidence:.2f}")
        print(f"{'='*60}\n")

    return 0 if result.is_valid else 1


def main():
    """CLI entrypoint."""
    try:
        exit_code = asyncio.run(main_async())
        exit(exit_code)
    except Exception as e:
        print(f"Error: {e}")
        exit(2)


if __name__ == "__main__":
    main()
