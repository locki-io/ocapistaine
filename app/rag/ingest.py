"""
Document ingestion pipeline.

Loads documents from JSONL, chunks them, and stores in ChromaDB.
Supports electoral program transcripts with list_name metadata.

Usage:
    python -m app.rag.ingest                    # Ingest all
    python -m app.rag.ingest --reset            # Clear and re-ingest
    python -m app.rag.ingest --file path.jsonl  # Ingest specific file
"""

import json
import hashlib
from pathlib import Path

from .store import get_collection, reset_collection

# RAG-optimized chunk size (smaller than field_input's 8k for better retrieval)
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200

DEFAULT_JSONL = Path(__file__).resolve().parents[2] / "data" / "audierne2026" / "rag" / "documents.jsonl"


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap
    return chunks


def make_chunk_id(doc_id: str, chunk_index: int) -> str:
    """Deterministic chunk ID."""
    raw = f"{doc_id}::chunk_{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    """Load documents from a JSONL file."""
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs


def ingest_documents(
    docs: list[dict],
    collection=None,
    batch_size: int = 100,
) -> dict:
    """
    Chunk and ingest documents into ChromaDB.

    Each doc should have at minimum: {id, content}
    Optional metadata: category, source_type, title, url, list_name
    """
    if collection is None:
        collection = get_collection()

    all_ids = []
    all_docs = []
    all_metas = []

    for doc in docs:
        doc_id = doc.get("id", "unknown")
        content = doc.get("content", "")
        if not content.strip():
            continue

        chunks = chunk_text(content)
        for i, chunk in enumerate(chunks):
            chunk_id = make_chunk_id(doc_id, i)
            metadata = {
                "doc_id": doc_id,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "category": doc.get("category", ""),
                "source_type": doc.get("source_type", ""),
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "list_name": doc.get("list_name", ""),
            }
            all_ids.append(chunk_id)
            all_docs.append(chunk)
            all_metas.append(metadata)

    # Batch upsert
    total = len(all_ids)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        collection.upsert(
            ids=all_ids[start:end],
            documents=all_docs[start:end],
            metadatas=all_metas[start:end],
        )

    return {
        "documents_processed": len(docs),
        "chunks_created": total,
        "collection_total": collection.count(),
    }


def ingest_from_jsonl(path: Path = DEFAULT_JSONL, reset: bool = False) -> dict:
    """Load a JSONL file and ingest into ChromaDB."""
    collection = reset_collection() if reset else get_collection()
    docs = load_jsonl(path)
    return ingest_documents(docs, collection)


def ingest_text(
    text: str,
    doc_id: str,
    list_name: str = "",
    category: str = "",
    source_type: str = "transcript",
    title: str = "",
) -> dict:
    """Ingest a single text document (e.g., an electoral program transcript)."""
    doc = {
        "id": doc_id,
        "content": text,
        "list_name": list_name,
        "category": category,
        "source_type": source_type,
        "title": title,
    }
    return ingest_documents([doc])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest documents into RAG vector store")
    parser.add_argument("--reset", action="store_true", help="Clear collection before ingesting")
    parser.add_argument("--file", type=str, default=None, help="JSONL file to ingest")
    args = parser.parse_args()

    path = Path(args.file) if args.file else DEFAULT_JSONL
    print(f"Ingesting from {path} (reset={args.reset})...")
    result = ingest_from_jsonl(path, reset=args.reset)
    print(f"Done: {result}")
