"""
Test fixtures: mock Embedder and Chunker so tests run without real model downloads.
Set MODULE_IMPL=mock or call monkeypatch fixtures directly.
"""
import hashlib
import pytest


class _MockEmbedder:
    dim = 1024

    def encode(self, texts, batch_size=32):
        return [[0.0] * self.dim for _ in texts]


class _MockChunker:
    def chunk(self, text: str):
        # Split on double-newlines for test predictability
        pieces = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not pieces:
            pieces = [text.strip()] if text.strip() else []
        return [(p, hashlib.sha256(p.encode()).hexdigest()) for p in pieces]


@pytest.fixture()
def mock_embedder():
    return _MockEmbedder()


@pytest.fixture()
def mock_chunker():
    return _MockChunker()


@pytest.fixture(autouse=True)
def _patch_lazy_singletons(monkeypatch):
    """
    Replace the module-level lazy getters so no GPU / model download occurs.
    """
    import app.routers.chunk_embed as ce
    monkeypatch.setattr(ce, "get_embedder", lambda: _MockEmbedder())
    monkeypatch.setattr(ce, "get_chunker", lambda: _MockChunker())
