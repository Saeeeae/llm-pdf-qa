import logging
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    logger.info("Loading embedding model: %s (device=%s)", settings.embed_model, settings.embed_device)
    return SentenceTransformer(settings.embed_model, device=settings.embed_device)


def embed_chunks(texts: list[str]) -> np.ndarray:
    """Embed document chunks with 'passage: ' prefix (required by E5 models).

    Returns ndarray of shape (N, 1024).
    """
    prefixed = [f"passage: {t}" for t in texts]
    model = _get_model()
    embeddings = model.encode(
        prefixed,
        normalize_embeddings=True,
        batch_size=settings.embed_batch_size,
        show_progress_bar=False,
    )
    return embeddings


def embed_query(query: str) -> np.ndarray:
    """Embed a search query with 'query: ' prefix (required by E5 models).

    Returns ndarray of shape (1024,).
    """
    model = _get_model()
    embedding = model.encode(
        [f"query: {query}"],
        normalize_embeddings=True,
    )
    return embedding[0]
