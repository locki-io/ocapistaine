"""
OCapistaine Agent — Result Models
"""

from pydantic import BaseModel, Field


class RetrievalMetrics(BaseModel):
    """Retrieval quality metrics computed from vector distances and result metadata."""

    chunks_found: int = 0
    best_distance: float = 0.0
    mean_distance: float = 0.0
    distance_spread: float = 0.0
    distance_gap_1_2: float = 0.0
    unique_docs: int = 0
    unique_lists: int = 0
    unique_categories: int = 0
    list_names: list[str] = Field(default_factory=list)
    total_context_chars: int = 0
    mean_chunk_chars: int = 0
    above_threshold_count: int = 0
    distances: list[float] = Field(default_factory=list)
    doc_ids: list[str] = Field(default_factory=list)


class ChatResult(BaseModel):
    """Result of a RAG Q&A query."""

    response: str
    sources: list[dict] = Field(default_factory=list)
    model: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    is_overview: bool = False
    thread_id: str = ""
    trace_id: str | None = None
    retrieval_metrics: RetrievalMetrics | None = None
    detected_category: str | None = None
    detected_list: str | None = None
    refined_query: str | None = None

    def to_dict(self) -> dict:
        return self.model_dump()


class CompareResult(BaseModel):
    """Result of a program comparison query."""

    response: str
    lists_compared: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    model: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    thread_id: str = ""
    trace_id: str | None = None
    retrieval_metrics: RetrievalMetrics | None = None

    def to_dict(self) -> dict:
        return self.model_dump()
