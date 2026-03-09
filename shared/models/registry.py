# shared/models/registry.py
import os
import logging
from dataclasses import dataclass, field
from sentence_transformers import SentenceTransformer, CrossEncoder

from shared.config import shared_settings

logger = logging.getLogger(__name__)


@dataclass
class ModelRegistry:
    _embedding: SentenceTransformer = field(default=None, init=False, repr=False)
    _reranker: CrossEncoder = field(default=None, init=False, repr=False)

    def embedding(self) -> SentenceTransformer:
        if self._embedding is None:
            model_dir = shared_settings.embedding_model_dir
            if os.path.isdir(model_dir) and os.listdir(model_dir):
                model_path = model_dir
            else:
                model_path = shared_settings.embedding_model_name
            logger.info("Loading embedding model: %s (device=%s)", model_path, shared_settings.embedding_device)
            self._embedding = SentenceTransformer(
                model_path,
                device=shared_settings.embedding_device,
                cache_folder=model_dir,
            )
        return self._embedding

    def reranker(self) -> CrossEncoder:
        if self._reranker is None:
            model_dir = shared_settings.reranker_model_dir
            if os.path.isdir(model_dir) and os.listdir(model_dir):
                model_path = model_dir
            else:
                model_path = shared_settings.reranker_model_name
            logger.info("Loading reranker model: %s (device=%s)", model_path, shared_settings.reranker_device)
            os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", model_dir)
            self._reranker = CrossEncoder(
                model_path,
                device=shared_settings.reranker_device,
            )
        return self._reranker


registry = ModelRegistry()
