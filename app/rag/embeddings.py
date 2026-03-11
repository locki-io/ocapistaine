"""
Embedding configuration for RAG pipeline.

Uses ChromaDB's built-in default embedding (all-MiniLM-L6-v2 via ONNX).
No external dependencies needed — works on Python 3.13+.
"""

# ChromaDB uses its default embedding function (all-MiniLM-L6-v2)
# when no embedding_function is specified. This handles multilingual
# content adequately for our scale (~100-1000 docs).
#
# To upgrade to a better French model later, implement a custom
# chromadb.EmbeddingFunction here and pass it to get_collection().
