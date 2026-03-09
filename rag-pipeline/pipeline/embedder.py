import logging
import numpy as np
from shared.models.registry import registry

logger = logging.getLogger(__name__)


def embed_chunks(texts: list[str]) -> np.ndarray:
    model = registry.embedding()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    )
    return embeddings


def embed_query(query: str) -> np.ndarray:
    model = registry.embedding()
    return model.encode([query], normalize_embeddings=True)[0]
