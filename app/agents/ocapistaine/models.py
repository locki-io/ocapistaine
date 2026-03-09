"""
OCapistaine Agent — Result Models
"""

from pydantic import BaseModel, Field


class ChatResult(BaseModel):
    """Result of a RAG Q&A query."""

    response: str
    sources: list[dict] = Field(default_factory=list)
    model: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    is_overview: bool = False
    thread_id: str = ""
    trace_id: str | None = None

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

    def to_dict(self) -> dict:
        return self.model_dump()
