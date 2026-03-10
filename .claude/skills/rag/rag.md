---
name: rag
description: "Use this skill when working with the RAG pipeline: diagnosing retrieval quality, optimizing chunking/embedding/retrieval, analyzing Opik traces for RAG metrics, managing ChromaDB store health, ingesting documents, or evolving the RAG architecture. Invoke whenever the user mentions 'RAG', 'retrieval', 'ChromaDB', 'embeddings', 'chunks', 'vector search', 'ingestion', 'retrieval quality', 'distance', 'density', 'confidence', or discusses comparison/chat response quality."
user_invocable: true
---

# Kvasir's RAG Skill

You are operating as **Kvasir**, the RAG specialist of the Vaettir realm. When this skill is invoked, focus entirely on the RAG pipeline domain.

## Quick Diagnostic Checklist

When a RAG quality issue is reported, follow this sequence:

### 1. Identify the symptom
- **Weak retrieval**: high distances, low density, above_threshold_count = 0
- **Missing list**: one list has no relevant chunks (check CSNF — only 6 chunks)
- **Wrong topic**: retrieved chunks don't match the question intent
- **Synthesis failure**: good retrieval but poor LLM response

### 2. Check the data layer
```bash
# Collection stats
python -c "from app.rag.store import collection_stats; print(collection_stats())"

# Check chunks per list
python -c "
from app.rag.store import get_collection
col = get_collection()
data = col.get(include=['metadatas'])
from collections import Counter
lists = Counter(m.get('list_name', '') for m in data['metadatas'])
cats = Counter(m.get('category', '') for m in data['metadatas'])
print('Lists:', dict(lists))
print('Categories:', dict(cats))
"
```

### 3. Test retrieval directly
```python
from app.rag.retrieval import search, search_compare

# Single query test
results = search("école Pierre-Le-Lec rénovation", n_results=10)
for r in results:
    print(f"  d={r.distance:.3f} list={r.metadata.get('list_name')} title={r.metadata.get('title','')[:50]}")

# Compare test
by_list = search_compare("pierre le lec", ["ca", "paa", "spae", "csnf"], n_per_list=5)
for name, results in by_list.items():
    print(f"\n{name}: {len(results)} chunks")
    for r in results:
        print(f"  d={r.distance:.3f} {r.content[:80]}...")
```

### 4. Diagnose and propose

Follow the cost ladder:
1. **Query refinement** (free) — improve the refiner prompt to expand topic-specific queries
2. **Metadata fix** (free) — fill empty category fields, correct list_name assignments
3. **Chunk enrichment** (cheap) — prepend topic headers to chunks during ingestion
4. **Increase n_per_list** (cheap) — retrieve more chunks to catch weak-but-relevant results
5. **Sentence-aware chunking** (medium) — split on section headers/paragraphs, not character count
6. **Multi-query retrieval** (medium) — generate 2-3 query variants, merge results
7. **French embeddings** (higher) — switch to a multilingual/French-specific model
8. **Re-ranking** (higher) — cross-encoder re-scoring of top-k results

## Key Files

| Component | Path | Purpose |
|-----------|------|---------|
| Store | `app/rag/store.py` | ChromaDB singleton, `get_collection()`, `collection_stats()` |
| Retrieval | `app/rag/retrieval.py` | `search()`, `search_overview()`, `search_compare()` |
| Ingestion | `app/rag/ingest.py` | `chunk_text()`, `ingest_documents()`, `ingest_from_jsonl()` |
| Embeddings | `app/rag/embeddings.py` | Config notes (uses ChromaDB default) |
| Prompts | `app/rag/prompts.py` | Synthesis prompts (Opik-synced with fallbacks) |
| Service | `app/rag/service.py` | `RAGService` — orchestrator with Opik tracing |
| Agent | `app/agents/ocapistaine/agent.py` | `OCapistaineAgent` — chat/compare with full tracing |
| Features | `app/agents/ocapistaine/features/` | Chat, Compare, Refine features |
| Metrics | `app/agents/ocapistaine/features/base.py` | `_compute_retrieval_metrics()`, `_RELEVANCE_THRESHOLD=0.5` |

## Current Stats (2026-03-10)

- **Collection**: `ocapistaine_docs`, 511 chunks, 171 documents
- **Embedding**: all-MiniLM-L6-v2 (ONNX, no GPU)
- **Chunk size**: 1500 chars, 200 overlap
- **Imbalance**: audierne2026=280 (55%), paa=55, ca=31, spae=27, csnf=6 (1%)
- **Gap**: 119 OCR chunks have empty category field
- **Threshold**: `_RELEVANCE_THRESHOLD = 0.5` (distance below which chunk is "confidently relevant")

## Retrieval Metrics Vocabulary

| Metric | Formula | Good | Bad |
|--------|---------|------|-----|
| confidence | `1 - best_distance` | > 0.7 | < 0.5 |
| density | `above_threshold / total` | > 0.6 | < 0.3 |
| diversity | `unique_docs / total` | > 0.5 | < 0.3 |
| spread | `max_distance - min_distance` | < 0.2 (tight) | > 0.3 (noisy) |
| gap_1_2 | `distance[1] - distance[0]` | > 0.05 (clear winner) | < 0.01 (ambiguous) |
