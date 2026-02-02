"""Build RAG index using MongoDB + ChromaDB with OpenAI embeddings."""

import json
import os
from pathlib import Path
from typing import Any
from datetime import datetime
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from openai import OpenAI
from pymongo import MongoClient, ASCENDING, DESCENDING
from config import EXT_DATA_DIR

# Load environment variables from .env file
load_dotenv()


def load_structured_documents() -> list[dict[str, Any]]:
    """
    Load structured documents from JSON.

    Returns:
        List of structured documents
    """
    structured_dir = EXT_DATA_DIR / "structured"
    all_docs_file = structured_dir / "all_documents.json"

    if not all_docs_file.exists():
        raise FileNotFoundError(
            f"Structured documents not found: {all_docs_file}\n"
            "Run structure_documents.py first!"
        )

    with all_docs_file.open("r", encoding="utf-8") as f:
        documents = json.load(f)

    print(f"✅ Loaded {len(documents)} structured documents")
    return documents


def setup_mongodb(mongo_uri: str = "mongodb://localhost:27017/") -> MongoClient:
    """
    Initialize MongoDB connection and setup database.

    Args:
        mongo_uri: MongoDB connection URI

    Returns:
        MongoDB client
    """
    print(f"\n{'='*60}")
    print(f"Setting up MongoDB")
    print(f"{'='*60}\n")

    client = MongoClient(mongo_uri)

    # Test connection
    try:
        client.admin.command('ping')
        print(f"✅ Connected to MongoDB at {mongo_uri}")
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        print(f"\n💡 Make sure MongoDB is running:")
        print(f"   brew services start mongodb-community")
        print(f"   or: docker run -d -p 27017:27017 mongo:latest")
        raise

    return client


def ingest_to_mongodb(
    client: MongoClient,
    documents: list[dict[str, Any]],
    db_name: str = "ocapistaine",
    collection_name: str = "municipal_documents",
) -> None:
    """
    Ingest structured documents into MongoDB.

    Args:
        client: MongoDB client
        documents: List of structured documents
        db_name: Database name
        collection_name: Collection name
    """
    print(f"\n{'='*60}")
    print(f"Ingesting Documents to MongoDB")
    print(f"{'='*60}\n")

    db = client[db_name]
    collection = db[collection_name]

    # Clear existing documents (fresh rebuild)
    existing_count = collection.count_documents({})
    if existing_count > 0:
        collection.delete_many({})
        print(f"🗑️  Deleted {existing_count} existing documents")

    # Prepare documents for MongoDB
    mongo_docs = []
    for doc in documents:
        mongo_doc = {
            "_id": doc["id"],  # Use our hash ID as MongoDB _id
            "content": doc["content"],
            "metadata": doc["metadata"],
            "indexed_at": datetime.utcnow(),
        }
        mongo_docs.append(mongo_doc)

    # Bulk insert
    if mongo_docs:
        result = collection.insert_many(mongo_docs, ordered=False)
        print(f"✅ Inserted {len(result.inserted_ids)} documents into MongoDB")

    # Create indexes for common queries
    collection.create_index([("metadata.category", ASCENDING)])
    collection.create_index([("metadata.date", DESCENDING)])
    collection.create_index([("metadata.title", ASCENDING)])
    collection.create_index([("indexed_at", DESCENDING)])
    print(f"✅ Created indexes on category, date, title, indexed_at")

    print(f"\n📊 MongoDB Summary:")
    print(f"   Database: {db_name}")
    print(f"   Collection: {collection_name}")
    print(f"   Total documents: {collection.count_documents({})}")


def initialize_vector_db(db_path: Path) -> chromadb.ClientAPI:
    """
    Initialize ChromaDB client.

    Args:
        db_path: Path to store the database

    Returns:
        ChromaDB client
    """
    db_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True,
        ),
    )

    print(f"✅ Initialized ChromaDB at {db_path}")
    return client


def chunk_document(
    doc: dict[str, Any],
    chunk_size: int = 1000,
    overlap: int = 100,
) -> list[dict[str, Any]]:
    """
    Split a document into overlapping chunks for better semantic search.

    Args:
        doc: Document with 'id', 'content', and 'metadata' fields
        chunk_size: Target size in tokens (default 1000)
        overlap: Overlap between chunks in tokens (default 100)

    Returns:
        List of chunk documents with parent reference
    """
    # Rough estimate: 1 token ≈ 4 characters for English/French
    chunk_chars = chunk_size * 4
    overlap_chars = overlap * 4

    content = doc["content"]
    chunks = []

    # If document is smaller than chunk_size, return as single chunk
    if len(content) <= chunk_chars:
        chunks.append({
            "id": f"{doc['id']}_chunk_0",
            "parent_id": doc["id"],
            "chunk_index": 0,
            "total_chunks": 1,
            "content": content,
            "metadata": doc["metadata"],
        })
        return chunks

    # Split into overlapping chunks
    start = 0
    chunk_index = 0

    while start < len(content):
        end = start + chunk_chars
        chunk_text = content[start:end]

        chunks.append({
            "id": f"{doc['id']}_chunk_{chunk_index}",
            "parent_id": doc["id"],
            "chunk_index": chunk_index,
            "total_chunks": -1,  # Will update after loop
            "content": chunk_text,
            "metadata": doc["metadata"],
        })

        chunk_index += 1
        start = end - overlap_chars  # Overlap for context continuity

        # Prevent infinite loop on very small overlaps
        if start >= len(content):
            break

    # Update total_chunks count
    total = len(chunks)
    for chunk in chunks:
        chunk["total_chunks"] = total

    return chunks


def build_vector_index(
    mongo_client: MongoClient,
    documents: list[dict[str, Any]],
    collection_name: str = "municipal_documents",
    model_name: str = "text-embedding-3-small",
    batch_size: int = 50,  # Reduced from 100
    db_name: str = "ocapistaine",
) -> None:
    """
    Build vector index from MongoDB documents using OpenAI embeddings.

    Args:
        mongo_client: MongoDB client
        documents: List of structured documents
        collection_name: Name of the ChromaDB collection
        model_name: OpenAI embedding model to use
        batch_size: Batch size for embedding generation
        db_name: MongoDB database name
    """
    print(f"\n{'='*60}")
    print(f"Building Vector Index")
    print(f"{'='*60}\n")

    # Check for OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY not found in environment.\n"
            "Please add it to your .env file:\n"
            "  OPENAI_API_KEY=sk-..."
        )

    # Initialize OpenAI client
    openai_client = OpenAI(api_key=api_key)
    print(f"✅ OpenAI client initialized\n")

    # Initialize vector database
    db_path = EXT_DATA_DIR / "vector_db"
    chroma_client = initialize_vector_db(db_path)

    # Delete existing collection if it exists (for fresh rebuild)
    try:
        chroma_client.delete_collection(name=collection_name)
        print(f"🗑️  Deleted existing ChromaDB collection: {collection_name}")
    except ValueError:
        pass

    # Create new collection
    collection = chroma_client.create_collection(
        name=collection_name,
        metadata={
            "description": "Municipal documents from Audierne (deliberations, arrêtés, commission reports)",
            "model": model_name,
            "mongodb_db": db_name,
            "mongodb_collection": "municipal_documents",
        },
    )
    print(f"✅ Created ChromaDB collection: {collection_name}\n")

    # Get embedding dimension
    embedding_dimension = 1536  # text-embedding-3-small dimension
    print(f"📐 Using OpenAI model: {model_name} (dimension: {embedding_dimension})\n")

    # Chunk all documents first
    print(f"📄 Chunking {len(documents)} documents...")
    all_chunks = []
    for doc in documents:
        chunks = chunk_document(doc, chunk_size=1000, overlap=100)
        all_chunks.extend(chunks)

    total_chunks = len(all_chunks)
    print(f"✅ Created {total_chunks} chunks from {len(documents)} documents")
    print(f"   Average: {total_chunks / len(documents):.1f} chunks per document\n")

    # Process chunks in batches
    print(f"🔄 Processing {total_chunks} chunks in batches of {batch_size}...\n")

    for start_idx in range(0, total_chunks, batch_size):
        end_idx = min(start_idx + batch_size, total_chunks)
        batch = all_chunks[start_idx:end_idx]

        # Extract content for embedding
        texts = [chunk["content"] for chunk in batch]

        # Generate embeddings using OpenAI API
        response = openai_client.embeddings.create(
            model=model_name,
            input=texts,
        )

        embeddings = [item.embedding for item in response.data]

        # Prepare data for ChromaDB
        ids = [chunk["id"] for chunk in batch]
        metadatas = []

        for chunk in batch:
            # ChromaDB metadata must be flat (no nested dicts)
            # Store chunk info + document metadata for filtering
            metadata = {
                "parent_id": chunk["parent_id"],  # Reference to MongoDB document
                "chunk_index": chunk["chunk_index"],
                "total_chunks": chunk["total_chunks"],
                "category": chunk["metadata"]["category"],
                "date": chunk["metadata"]["date"] or "",
                "title": chunk["metadata"]["title"][:200],  # Truncate for ChromaDB limits
                "language": chunk["metadata"]["language"],
            }
            metadatas.append(metadata)

        # Add to collection
        # Note: We store chunk text in ChromaDB, full documents are in MongoDB
        collection.add(
            ids=ids,
            embeddings=embeddings,  # Already lists from OpenAI API
            metadatas=metadatas,
            documents=[chunk["content"][:1000] + "..." for chunk in batch],  # Preview
        )

        batch_num = start_idx // batch_size + 1
        total_batches = (total_chunks + batch_size - 1) // batch_size
        print(f"  ✅ Batch {batch_num}/{total_batches}: Indexed {len(batch)} chunks ({start_idx + 1}-{end_idx})")

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Vector Index Building Complete")
    print(f"{'='*60}")
    print(f"  ✅ Total chunks indexed: {collection.count()}")
    print(f"  📄 Source documents: {len(documents)}")
    print(f"  📁 Vector database location: {db_path}")
    print(f"  🔍 Collection name: {collection_name}")
    print(f"  🤖 Embedding model: {model_name}")
    print(f"  📏 Embedding dimension: {embedding_dimension}")
    print(f"  🔗 Chunk size: 1000 tokens (~4,000 chars)")
    print(f"  ↔️  Chunk overlap: 100 tokens (~400 chars)")


def main():
    """Main RAG index building process."""

    # Load structured documents
    documents = load_structured_documents()

    # Setup MongoDB
    mongo_client = setup_mongodb()

    # Ingest to MongoDB (source of truth)
    ingest_to_mongodb(mongo_client, documents)

    # Build vector index from MongoDB documents
    build_vector_index(mongo_client, documents)

    print(f"\n{'='*60}")
    print(f"🎉 RAG System Setup Complete!")
    print(f"{'='*60}")
    print(f"\n📊 System Overview:")
    print(f"   MongoDB: Source of truth with {len(documents)} documents")
    print(f"   ChromaDB: Vector search index with embeddings")

    # Close MongoDB connection
    mongo_client.close()


if __name__ == "__main__":
    main()
