import hashlib
import os
from typing import List, Optional

_MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-m3")


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


def _safe_batch_size(default: int = 32) -> int:
    """Return a safe batch size based on available GPU memory."""
    try:
        import torch
        if not torch.cuda.is_available():
            return default
        free, total = torch.cuda.mem_get_info()
        # If free GPU memory < 4 GB, halve the batch size
        if free < 4 * 1024 ** 3:
            return max(8, default // 2)
        return default
    except Exception:
        return default


class Embedder:
    def __init__(self, model_name: str = _MODEL_NAME, device: Optional[str] = None):
        # Import deferred so startup doesn't fail when torch/sentence-transformers
        # are not installed or the model hasn't been downloaded yet.
        from sentence_transformers import SentenceTransformer
        resolved = _resolve_device(device or os.getenv("EMBED_DEVICE"))
        self.model = SentenceTransformer(model_name, device=resolved)
        self.device = resolved
        self.dim = 1024

    def encode(self, texts: List[str], batch_size: Optional[int] = None) -> List[List[float]]:
        if batch_size is None:
            batch_size = _safe_batch_size()
        return self.model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True
        ).tolist()
