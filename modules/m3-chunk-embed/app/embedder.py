import hashlib
from typing import List, Optional

_MODEL_NAME = "BAAI/bge-m3"


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
    def __init__(self, model_name: str = _MODEL_NAME, device: str = "cuda:0"):
        # Import deferred so startup doesn't fail when torch/sentence-transformers
        # are not installed or the model hasn't been downloaded yet.
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name, device=device)
        self.dim = 1024

    def encode(self, texts: List[str], batch_size: Optional[int] = None) -> List[List[float]]:
        if batch_size is None:
            batch_size = _safe_batch_size()
        return self.model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True
        ).tolist()
