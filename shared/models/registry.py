# shared/models/registry.py
import os
import logging
from dataclasses import dataclass, field
import hashlib
from typing import Any

import numpy as np

from shared.config import shared_settings

logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> list[str]:
    return [token for token in value.lower().split() if token]


class SmokeEmbeddingModel:
    dim = 1024

    def encode(self, inputs, normalize_embeddings: bool = True, **kwargs):
        if isinstance(inputs, str):
            return self._encode_text(inputs, normalize_embeddings=normalize_embeddings)
        return np.vstack([
            self._encode_text(text, normalize_embeddings=normalize_embeddings)
            for text in inputs
        ])

    def _encode_text(self, text: str, normalize_embeddings: bool = True) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = _normalize_text(text) or [text.strip().lower() or "__empty__"]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for idx in range(0, min(len(digest), 16), 2):
                bucket = ((digest[idx] << 8) + digest[idx + 1]) % self.dim
                vec[bucket] += 1.0
        if normalize_embeddings:
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
        return vec


class SmokeRerankerModel:
    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        scores: list[float] = []
        for query, content in pairs:
            q_tokens = set(_normalize_text(query))
            c_tokens = set(_normalize_text(content))
            overlap = len(q_tokens & c_tokens)
            score = overlap / max(len(q_tokens), 1)
            if query and query.lower() in content.lower():
                score += 0.5
            scores.append(float(score))
        return scores


@dataclass
class ModelRegistry:
    _embedding: Any = field(default=None, init=False, repr=False)
    _reranker: Any = field(default=None, init=False, repr=False)

    def embedding(self):
        if self._embedding is None:
            if shared_settings.smoke_test_mode:
                logger.warning("SMOKE_TEST_MODE enabled; using fallback embedding model")
                self._embedding = SmokeEmbeddingModel()
                return self._embedding
            from sentence_transformers import SentenceTransformer
            model_dir = shared_settings.embedding_model_dir
            if os.path.isdir(model_dir) and os.listdir(model_dir):
                model_path = model_dir
            else:
                model_path = shared_settings.embedding_model_name
            logger.info("Loading embedding model: %s (device=%s)", model_path, shared_settings.embedding_device)
            try:
                self._embedding = SentenceTransformer(
                    model_path,
                    device=shared_settings.embedding_device,
                    cache_folder=model_dir,
                )
            except Exception as exc:
                logger.warning("Falling back to smoke embedding model: %s", exc)
                self._embedding = SmokeEmbeddingModel()
        return self._embedding

    def reranker(self):
        if self._reranker is None:
            if shared_settings.smoke_test_mode:
                logger.warning("SMOKE_TEST_MODE enabled; using fallback reranker")
                self._reranker = SmokeRerankerModel()
                return self._reranker
            from sentence_transformers import CrossEncoder
            model_dir = shared_settings.reranker_model_dir
            if os.path.isdir(model_dir) and os.listdir(model_dir):
                model_path = model_dir
            else:
                model_path = shared_settings.reranker_model_name
            logger.info("Loading reranker model: %s (device=%s)", model_path, shared_settings.reranker_device)
            os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", model_dir)
            try:
                self._reranker = CrossEncoder(
                    model_path,
                    device=shared_settings.reranker_device,
                )
            except Exception as exc:
                logger.warning("Falling back to smoke reranker: %s", exc)
                self._reranker = SmokeRerankerModel()
        return self._reranker


registry = ModelRegistry()
