"""Unit tests for Embedder using a mock SentenceTransformer — no GPU needed."""
import numpy as np
import pytest


class _FakeSentenceTransformer:
    def encode(self, texts, batch_size=32, normalize_embeddings=True):
        return np.zeros((len(texts), 1024), dtype=np.float32)


def _make_embedder(model_name="BAAI/bge-m3", device="cpu"):
    from app.embedder import Embedder
    e = Embedder.__new__(Embedder)
    e.model = _FakeSentenceTransformer()
    e.dim = 1024
    return e


def test_encode_returns_list_of_lists():
    emb = _make_embedder()
    result = emb.encode(["hello", "world"])
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], list)


def test_encode_dim():
    emb = _make_embedder()
    result = emb.encode(["test sentence"])
    assert len(result[0]) == 1024


def test_encode_zero_vector_mock():
    emb = _make_embedder()
    result = emb.encode(["anything"])
    assert all(v == 0.0 for v in result[0])


def test_encode_batch_size_respected():
    emb = _make_embedder()
    texts = [f"sentence {i}" for i in range(100)]
    result = emb.encode(texts, batch_size=16)
    assert len(result) == 100


def test_encode_empty():
    emb = _make_embedder()
    result = emb.encode([])
    assert result == []
