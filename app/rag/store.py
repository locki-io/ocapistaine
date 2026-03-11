"""
ChromaDB vector store wrapper.

Manages document storage and retrieval with persistent local storage.
Uses ChromaDB's default embedding (all-MiniLM-L6-v2 via ONNX).
"""

import os
from pathlib import Path

import chromadb

COLLECTION_NAME = "ocapistaine_docs"
PERSIST_DIR = os.environ.get(
    "CHROMADB_PERSIST_DIR",
    str(Path(__file__).resolve().parents[2] / "data" / "chromadb"),
)

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def get_collection() -> chromadb.Collection:
    """Get or create the ChromaDB collection (singleton)."""
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=PERSIST_DIR)
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def reset_collection() -> chromadb.Collection:
    """Delete and recreate the collection (for re-ingestion)."""
    global _client, _collection
    _client = chromadb.PersistentClient(path=PERSIST_DIR)
    try:
        _client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    _collection = _client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def collection_stats() -> dict:
    """Get collection statistics."""
    col = get_collection()
    count = col.count()
    return {
        "total_chunks": count,
        "collection": COLLECTION_NAME,
        "persist_dir": PERSIST_DIR,
    }
