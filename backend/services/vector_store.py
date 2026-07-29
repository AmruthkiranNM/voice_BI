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

# Keyed by user id (None outside a request, e.g. tests/startup) so each
# account's schema embeddings stay in their own in-memory index and never
# leak into another user's RAG search results.
_indexes: dict[int | None, "faiss.IndexFlatIP"] = {}
_documents: dict[int | None, list[dict[str, str]]] = {}


def _current_user():
    from services.auth import current_user_id
    return current_user_id.get()


def _store_dir(user_id) -> Path:
    subdir = str(user_id) if user_id is not None else "default"
    return Path(VECTOR_STORE_DIR) / subdir


def build_index(schema_documents: list[dict[str, str]]) -> None:
    """
    Build a FAISS index from schema documents.

    Each document is embedded and stored in a flat inner-product index
    (cosine similarity since embeddings are L2-normalized).

    Args:
        schema_documents: List of dicts with "table_name" and "document".
    """
    if not schema_documents:
        raise ValueError("No schema documents provided to build index.")

    user_id = _current_user()
    texts = [doc["document"] for doc in schema_documents]

    logger.info("Generating embeddings for %d schema documents...", len(texts))
    embeddings = generate_embeddings_batch(texts)

    # Build FAISS index (Inner Product for cosine similarity with normalized vectors)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings.astype(np.float32))

    _indexes[user_id] = index
    _documents[user_id] = schema_documents
    _save_to_disk(user_id, index, schema_documents)

    logger.info(
        "FAISS index built: %d vectors, dimension=%d",
        index.ntotal, dimension,
    )


def _save_to_disk(user_id, index, documents: list[dict[str, str]]) -> None:
    """Save the FAISS index and document metadata to disk."""
    store_dir = _store_dir(user_id)
    store_dir.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(store_dir / "schema.index"))

    with open(store_dir / "documents.json", "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2)

    logger.info("Vector store saved to %s", store_dir)


def load_index() -> bool:
    """
    Load persisted FAISS index and documents from disk.

    Returns:
        True if loaded successfully, False otherwise.
    """
    user_id = _current_user()
    store_dir = _store_dir(user_id)
    index_path = store_dir / "schema.index"
    docs_path = store_dir / "documents.json"

    if not index_path.exists() or not docs_path.exists():
        logger.info("No persisted vector store found.")
        return False

    _indexes[user_id] = faiss.read_index(str(index_path))

    with open(docs_path, "r", encoding="utf-8") as f:
        _documents[user_id] = json.load(f)

    logger.info(
        "Loaded vector store: %d vectors, %d documents",
        _indexes[user_id].ntotal, len(_documents[user_id]),
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
    user_id = _current_user()
    index = _indexes.get(user_id)
    documents = _documents.get(user_id, [])

    if index is None or index.ntotal == 0:
        raise RuntimeError(
            "Vector store not initialized. Call build_index() or load_index() first."
        )

    if top_k is None:
        top_k = RAG_TOP_K

    # Clamp top_k to available documents
    top_k = min(top_k, index.ntotal)

    query_embedding = generate_embedding(query).astype(np.float32).reshape(1, -1)
    scores, indices = index.search(query_embedding, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(documents):
            continue
        results.append({
            "table_name": documents[idx]["table_name"],
            "document": documents[idx]["document"],
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
    """
    Check if the FAISS index is loaded and ready for queries. Lazily loads
    it from disk on first use per user/process (e.g. after a server
    restart, or the first request for this user in a fresh process).
    """
    user_id = _current_user()
    index = _indexes.get(user_id)
    if index is None:
        load_index()
        index = _indexes.get(user_id)
    return index is not None and index.ntotal > 0
