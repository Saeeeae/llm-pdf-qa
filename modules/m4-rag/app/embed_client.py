"""Query-side embedder for m4-rag.

Mirrors m3's device resolution: explicit > EMBED_DEVICE env > auto-detect.
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


class QueryEmbedder:
    _instance: Optional["QueryEmbedder"] = None

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
        device = _resolve_device(os.getenv("EMBED_DEVICE"))
        self.model = SentenceTransformer(model_name, device=device)
        self.device = device

    @classmethod
    def get(cls) -> "QueryEmbedder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def encode(self, q: str) -> List[float]:
        return self.model.encode([q], normalize_embeddings=True)[0].tolist()
