"""
Vector Store Service Module

Manages the FAISS vector index for schema document retrieval.
Supports building the index from schema documents and querying
for the most relevant schema chunks given a natural language query.
"""

import logging
import json
import numpy as np
import faiss
from pathlib import Path

from config import VECTOR_STORE_DIR, RAG_TOP_K
from services.embeddings import generate_embeddings_batch, generate_embedding

logger = logging.getLogger(__name__)

# Module-level state
_index: faiss.IndexFlatIP | None = None
_documents: list[dict[str, str]] = []


def build_index(schema_documents: list[dict[str, str]]) -> None:
    """
    Build a FAISS index from schema documents.

    Each document is embedded and stored in a flat inner-product index
    (cosine similarity since embeddings are L2-normalized).

    Args:
        schema_documents: List of dicts with "table_name" and "document".
    """
    global _index, _documents

    if not schema_documents:
        raise ValueError("No schema documents provided to build index.")

    _documents = schema_documents
    texts = [doc["document"] for doc in schema_documents]

    logger.info("Generating embeddings for %d schema documents...", len(texts))
    embeddings = generate_embeddings_batch(texts)

    # Build FAISS index (Inner Product for cosine similarity with normalized vectors)
    dimension = embeddings.shape[1]
    _index = faiss.IndexFlatIP(dimension)
    _index.add(embeddings.astype(np.float32))

    # Persist index and metadata to disk
    _save_to_disk(embeddings)

    logger.info(
        "FAISS index built: %d vectors, dimension=%d",
        _index.ntotal, dimension,
    )


def _save_to_disk(embeddings: np.ndarray) -> None:
    """Save the FAISS index and document metadata to disk."""
    store_dir = Path(VECTOR_STORE_DIR)
    store_dir.mkdir(parents=True, exist_ok=True)

    # Save FAISS index
    faiss.write_index(_index, str(store_dir / "schema.index"))

    # Save document metadata
    with open(store_dir / "documents.json", "w", encoding="utf-8") as f:
        json.dump(_documents, f, indent=2)

    logger.info("Vector store saved to %s", store_dir)


def load_index() -> bool:
    """
    Load persisted FAISS index and documents from disk.

    Returns:
        True if loaded successfully, False otherwise.
    """
    global _index, _documents

    store_dir = Path(VECTOR_STORE_DIR)
    index_path = store_dir / "schema.index"
    docs_path = store_dir / "documents.json"

    if not index_path.exists() or not docs_path.exists():
        logger.info("No persisted vector store found.")
        return False

    _index = faiss.read_index(str(index_path))

    with open(docs_path, "r", encoding="utf-8") as f:
        _documents = json.load(f)

    logger.info(
        "Loaded vector store: %d vectors, %d documents",
        _index.ntotal, len(_documents),
    )
    return True


def search(query: str, top_k: int | None = None) -> list[dict]:
    """
    Search the FAISS index for schema documents most relevant to the query.

    Args:
        query: Natural language query string.
        top_k: Number of results to return. Defaults to RAG_TOP_K config.

    Returns:
        List of dicts with "table_name", "document", and "score".
    """
    if _index is None or _index.ntotal == 0:
        raise RuntimeError(
            "Vector store not initialized. Call build_index() or load_index() first."
        )

    if top_k is None:
        top_k = RAG_TOP_K

    # Clamp top_k to available documents
    top_k = min(top_k, _index.ntotal)

    query_embedding = generate_embedding(query).astype(np.float32).reshape(1, -1)
    scores, indices = _index.search(query_embedding, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(_documents):
            continue
        results.append({
            "table_name": _documents[idx]["table_name"],
            "document": _documents[idx]["document"],
            "similarity_score": float(score),
        })

    logger.info(
        "RAG search for '%s': found %d results (top scores: %s)",
        query[:60],
        len(results),
        [f"{r['similarity_score']:.3f}" for r in results[:3]],
    )

    return results


def is_index_ready() -> bool:
    """Check if the FAISS index is loaded and ready for queries."""
    return _index is not None and _index.ntotal > 0
