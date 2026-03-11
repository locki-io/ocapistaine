"""
RAG (Retrieval Augmented Generation) pipeline for OCapistaine.

Provides semantic search over municipal documents and citizen contributions
to answer questions about Audierne local governance.
"""

from .service import RAGService

__all__ = ["RAGService"]
