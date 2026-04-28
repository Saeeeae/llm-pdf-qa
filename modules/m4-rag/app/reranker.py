"""Cross-encoder reranker (BAAI/bge-reranker-v2-m3 by default).

Used after coarse RRF retrieval to score (query, candidate_text) pairs more
precisely. Scores are min-max normalized to [0, 1] and combined with the
fused RRF score via RERANK_ALPHA.
"""
from __future__ import annotations

import os
from typing import List, Optional


def _resolve_device(requested: Optional[str]) -> str:
    if requested and requested != "auto":
        return requested
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu"


class Reranker:
    """Singleton wrapper around a CrossEncoder."""

    _instance: Optional["Reranker"] = None

    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None):
        from sentence_transformers import CrossEncoder
        self.model_name = model_name or os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
        self.device = _resolve_device(device or os.getenv("RERANK_DEVICE"))
        self.model = CrossEncoder(self.model_name, device=self.device, max_length=512)

    @classmethod
    def get(cls) -> "Reranker":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def score(self, query: str, texts: List[str], batch_size: int = 32) -> List[float]:
        """Return raw cross-encoder logits for each (query, text) pair."""
        if not texts:
            return []
        pairs = [(query, t) for t in texts]
        return [float(s) for s in self.model.predict(pairs, batch_size=batch_size)]


def normalize(scores: List[float]) -> List[float]:
    """Min-max normalize to [0, 1]; constant inputs map to 0.5."""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [0.5] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]
