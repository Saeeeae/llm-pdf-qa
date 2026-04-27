import os
from typing import List


class QueryEmbedder:
    _instance = None

    def __init__(self):
        # Lazy import: model loaded once at first encode call
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(os.getenv("EMBED_MODEL", "BAAI/bge-m3"))

    @classmethod
    def get(cls) -> "QueryEmbedder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def encode(self, q: str) -> List[float]:
        return self.model.encode([q], normalize_embeddings=True)[0].tolist()
