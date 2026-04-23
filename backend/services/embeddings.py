"""
Embedding Service Module

Generates vector embeddings for text using sentence-transformers.
Used to embed both schema documents and user queries for RAG retrieval.
"""

import logging
import numpy as np
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

# Singleton model instance — loaded once, reused across requests
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Load and cache the sentence-transformer embedding model."""
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully.")
    return _model


def generate_embedding(text: str) -> np.ndarray:
    """
    Generate a single embedding vector for the given text.

    Args:
        text: Input string to embed.

    Returns:
        NumPy array of shape (embedding_dim,)
    """
    model = get_model()
    embedding = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return embedding


def generate_embeddings_batch(texts: list[str]) -> np.ndarray:
    """
    Generate embeddings for a batch of texts.

    Args:
        texts: List of input strings.

    Returns:
        NumPy array of shape (n_texts, embedding_dim)
    """
    model = get_model()
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings
