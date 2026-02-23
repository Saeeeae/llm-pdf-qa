import logging
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    import os

    # 로컬 마운트 경로에 모델이 있으면 우선 사용
    local_path = settings.embedding_model_dir
    if os.path.isdir(local_path) and os.listdir(local_path):
        model_path = local_path
        logger.info("Loading embedding model from local: %s (device=%s)", model_path, settings.embed_device)
    else:
        model_path = settings.embed_model
        logger.info("Loading embedding model from HuggingFace: %s (device=%s)", model_path, settings.embed_device)

    return SentenceTransformer(model_path, device=settings.embed_device)


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
