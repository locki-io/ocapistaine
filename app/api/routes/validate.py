"""
Validation API Routes

REST endpoints for charter validation using Forseti 461 agent.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.forseti import (
    ForsetiAgent,
    BatchItem,
    BatchResult,
    CATEGORIES,
)


router = APIRouter(prefix="/validate", tags=["validation"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ValidateRequest(BaseModel):
    """Request model for single contribution validation."""

    title: str = Field(description="Contribution title")
    body: str = Field(description="Contribution body/content")
    category: str | None = Field(
        default=None,
        description="Optional existing category",
    )
    provider: str | None = Field(
        default=None,
        description="LLM provider to use (gemini, claude, mistral, ollama)",
    )


class ValidateResponse(BaseModel):
    """Response model for single contribution validation."""

    is_valid: bool
    category: str
    original_category: str | None
    violations: list[str]
    encouraged_aspects: list[str]
    reasoning: str
    confidence: float


class CharterValidateRequest(BaseModel):
    """Request model for charter-only validation."""

    title: str
    body: str


class CharterValidateResponse(BaseModel):
    """Response model for charter-only validation."""

    is_valid: bool
    violations: list[str]
    encouraged_aspects: list[str]
    reasoning: str
    confidence: float


class ClassifyRequest(BaseModel):
    """Request model for category classification."""

    title: str
    body: str
    current_category: str | None = None


class ClassifyResponse(BaseModel):
    """Response model for category classification."""

    category: str
    reasoning: str
    confidence: float


class BatchValidateRequest(BaseModel):
    """Request model for batch validation."""

    items: list[BatchItem]
    provider: str | None = None


class BatchValidateResponse(BaseModel):
    """Response model for batch validation."""

    results: list[BatchResult]
    total: int
    valid_count: int
    invalid_count: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=ValidateResponse)
async def validate_contribution(request: ValidateRequest) -> ValidateResponse:
    """
    Validate a citizen contribution.

    Performs:
    - Charter compliance validation
    - Category classification

    Returns validation result with assigned category.
    """
    try:
        agent = ForsetiAgent(provider_name=request.provider)
        result = await agent.validate(
            title=request.title,
            body=request.body,
            category=request.category,
        )
        return ValidateResponse(
            is_valid=result.is_valid,
            category=result.category,
            original_category=result.original_category,
            violations=result.violations,
            encouraged_aspects=result.encouraged_aspects,
            reasoning=result.reasoning,
            confidence=result.confidence,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation error: {e}")


@router.post("/charter", response_model=CharterValidateResponse)
async def validate_charter_only(
    request: CharterValidateRequest,
) -> CharterValidateResponse:
    """
    Validate charter compliance only (no category classification).

    Faster than full validation when category is not needed.
    """
    try:
        agent = ForsetiAgent()
        result = await agent.validate_charter(
            title=request.title,
            body=request.body,
        )
        return CharterValidateResponse(
            is_valid=result.is_valid,
            violations=result.violations,
            encouraged_aspects=result.encouraged_aspects,
            reasoning=result.reasoning,
            confidence=result.confidence,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation error: {e}")


@router.post("/classify", response_model=ClassifyResponse)
async def classify_category(request: ClassifyRequest) -> ClassifyResponse:
    """
    Classify a contribution into one of 7 categories.

    Categories: economie, logement, culture, ecologie, associations,
    jeunesse, alimentation-bien-etre-soins
    """
    try:
        agent = ForsetiAgent()
        result = await agent.classify_category(
            title=request.title,
            body=request.body,
            current_category=request.current_category,
        )
        return ClassifyResponse(
            category=result.category,
            reasoning=result.reasoning,
            confidence=result.confidence,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification error: {e}")


@router.post("/batch", response_model=BatchValidateResponse)
async def validate_batch(request: BatchValidateRequest) -> BatchValidateResponse:
    """
    Validate multiple contributions in a single request.

    More efficient than individual calls for bulk processing.
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="No items provided")

    if len(request.items) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 items per batch",
        )

    try:
        agent = ForsetiAgent(provider_name=request.provider)
        results = await agent.validate_batch(request.items)

        valid_count = sum(1 for r in results if r.is_valid)

        return BatchValidateResponse(
            results=results,
            total=len(results),
            valid_count=valid_count,
            invalid_count=len(results) - valid_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch validation error: {e}")


@router.get("/categories")
async def list_categories() -> dict:
    """
    List all available categories.

    Returns the 7 categories with descriptions.
    """
    return {
        "categories": CATEGORIES,
        "descriptions": {
            "economie": "Business, port, tourism, local economy",
            "logement": "Housing, real estate, urban planning",
            "culture": "Heritage, events, arts, traditions",
            "ecologie": "Environment, sustainability, nature",
            "associations": "Community organizations, clubs",
            "jeunesse": "Youth, schools, education, children",
            "alimentation-bien-etre-soins": "Food, health, wellness, medical",
        },
    }
