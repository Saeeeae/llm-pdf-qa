"""Test fixtures.

Replaces lazy singletons in app.routers.chunk_embed so the suite runs without
loading real models. The mock chunker mirrors the new hierarchical API:
returns (parents, leaves) lists.
"""
import hashlib

import pytest

from app.chunker import LeafChunk, ParentChunk


class _MockEmbedder:
    dim = 1024

    def encode(self, texts, batch_size=32):
        return [[0.0] * self.dim for _ in texts]


class _MockChunker:
    """Splits on blank lines. Each non-empty paragraph becomes one parent
    AND one leaf (1:1) — keeps the test arithmetic simple while exercising
    both insertion paths in the router.
    """

    def chunk(self, text: str):
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        parents = []
        leaves = []
        for i, p in enumerate(paras):
            parents.append(ParentChunk(idx=i, text=p, start=i, end=i + 1))
            h = hashlib.sha256(p.encode()).hexdigest()
            leaves.append(
                LeafChunk(idx=i, text=p, chunk_hash=h, parent_idx=i, start=i, end=i + 1)
            )
        return parents, leaves


@pytest.fixture()
def mock_embedder():
    return _MockEmbedder()


@pytest.fixture()
def mock_chunker():
    return _MockChunker()


@pytest.fixture(autouse=True)
def _patch_lazy_singletons(monkeypatch):
    import app.routers.chunk_embed as ce
    monkeypatch.setattr(ce, "get_embedder", lambda: _MockEmbedder())
    monkeypatch.setattr(ce, "get_chunker", lambda: _MockChunker())
