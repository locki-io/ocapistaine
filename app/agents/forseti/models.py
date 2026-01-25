"""
Forseti Agent Models

Pydantic models for validation and classification results.
"""

from pydantic import BaseModel, Field


# Charter categories for Audierne-Esquibien
CATEGORIES = [
    "economie",
    "logement",
    "culture",
    "ecologie",
    "associations",
    "jeunesse",
    "alimentation-bien-etre-soins",
]

# What the charter prohibits
CHARTER_VIOLATIONS = [
    "Personal attacks or discriminatory remarks",
    "Spam or advertising",
    "Proposals unrelated to Audierne-Esquibien",
    "False information",
]

# What the charter encourages
CHARTER_ENCOURAGED = [
    "Concrete and argued proposals",
    "Constructive criticism",
    "Questions and requests for clarification",
    "Sharing of experiences and expertise",
    "Suggestions for improvement",
]


class ValidationResult(BaseModel):
    """Result of charter validation for a contribution."""

    is_valid: bool = Field(
        description="Whether the contribution complies with the charter"
    )
    violations: list[str] = Field(
        default_factory=list,
        description="List of charter violations found",
    )
    encouraged_aspects: list[str] = Field(
        default_factory=list,
        description="Positive aspects that align with charter values",
    )
    reasoning: str = Field(
        default="",
        description="Explanation of the validation decision",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score for the validation (0.0-1.0)",
    )


class ClassificationResult(BaseModel):
    """Result of category classification for a contribution."""

    category: str = Field(
        description="Assigned category from the predefined list"
    )
    reasoning: str = Field(
        default="",
        description="Explanation of the classification decision",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score for the classification (0.0-1.0)",
    )


class WordingResult(BaseModel):
    """Result of wording correction/improvement."""

    original: str = Field(description="Original text")
    corrected: str = Field(description="Corrected/improved text")
    changes: list[str] = Field(
        default_factory=list,
        description="List of changes made",
    )
    reasoning: str = Field(
        default="",
        description="Explanation of corrections",
    )


class FullValidationResult(BaseModel):
    """Combined result of validation and classification."""

    is_valid: bool = Field(
        description="Whether the contribution complies with the charter"
    )
    category: str = Field(
        description="Assigned category"
    )
    original_category: str | None = Field(
        default=None,
        description="Original category if provided",
    )
    violations: list[str] = Field(
        default_factory=list,
        description="Charter violations found",
    )
    encouraged_aspects: list[str] = Field(
        default_factory=list,
        description="Positive aspects",
    )
    reasoning: str = Field(
        default="",
        description="Combined reasoning",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Overall confidence",
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()


class ContributionInput(BaseModel):
    """Input model for a citizen contribution."""

    title: str = Field(description="Contribution title")
    body: str = Field(description="Contribution body/content")
    category: str | None = Field(
        default=None,
        description="Optional existing category",
    )

    @property
    def text(self) -> str:
        """Combined text for analysis."""
        return f"{self.title}\n\n{self.body}"


class BatchItem(BaseModel):
    """Single item in a batch validation request."""

    id: str = Field(description="Unique identifier")
    title: str = Field(description="Item title")
    body: str = Field(description="Item body")
    category: str | None = Field(default=None)


class BatchResult(BaseModel):
    """Result for a single item in batch processing."""

    id: str = Field(description="Item identifier")
    is_valid: bool = Field(default=True)
    violations: list[str] = Field(default_factory=list)
    encouraged_aspects: list[str] = Field(default_factory=list)
    category: str = Field(default="economie")
    reasoning: str = Field(default="")
    confidence: float = Field(default=0.5)
