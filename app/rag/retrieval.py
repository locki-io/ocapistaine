"""
Retrieval module — query the vector store and return ranked results.
"""

import random
from dataclasses import dataclass

from .store import get_collection


@dataclass
class RetrievalResult:
    content: str
    metadata: dict
    distance: float


def search(
    query: str,
    n_results: int = 5,
    where: dict | None = None,
) -> list[RetrievalResult]:
    """
    Search the vector store for relevant chunks.

    Args:
        query: User question in natural language
        n_results: Number of results to return
        where: Optional ChromaDB metadata filter, e.g. {"list_name": "audierne2026"}

    Returns:
        List of RetrievalResult sorted by relevance
    """
    collection = get_collection()
    if collection.count() == 0:
        return []

    kwargs = {
        "query_texts": [query],
        "n_results": min(n_results, collection.count()),
    }
    if where:
        # Filter out empty values
        clean_where = {k: v for k, v in where.items() if v}
        if clean_where:
            kwargs["where"] = clean_where

    results = collection.query(**kwargs)

    items = []
    for i in range(len(results["ids"][0])):
        items.append(
            RetrievalResult(
                content=results["documents"][0][i],
                metadata=results["metadatas"][0][i],
                distance=results["distances"][0][i] if results.get("distances") else 0.0,
            )
        )
    return items


def search_overview(
    query: str,
    n_per_list: int = 2,
) -> list[RetrievalResult]:
    """
    Overview retrieval: reference doc + top chunks from each list.

    Used for broad questions about the elections that need a panoramic view
    rather than deep results from a single list.
    """
    all_results = []

    # 1. Always include the reference document
    ref_results = search(query, n_results=3, where={"category": "reference"})
    all_results.extend(ref_results)

    # 2. Get top chunks from each list (shuffled for neutrality)
    list_names = ["audierne2026", "ca", "paa", "spae", "csnf"]
    random.shuffle(list_names)
    for name in list_names:
        results = search(query, n_results=n_per_list, where={"list_name": name})
        all_results.extend(results)

    # Deduplicate by content (same chunk can appear in reference + list)
    seen_ids = set()
    deduped = []
    for r in all_results:
        chunk_id = r.metadata.get("doc_id", "") + str(r.metadata.get("chunk_index", ""))
        if chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            deduped.append(r)

    return deduped


def search_compare(
    query: str,
    list_names: list[str],
    n_per_list: int = 3,
) -> dict[str, list[RetrievalResult]]:
    """
    Search across multiple electoral lists for comparison.

    Returns a dict of list_name -> results.
    """
    results = {}
    for name in list_names:
        results[name] = search(query, n_results=n_per_list, where={"list_name": name})
    return results
