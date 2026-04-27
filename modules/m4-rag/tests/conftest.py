import os
os.environ["TEST_MODE"] = "1"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["VLLM_URL"] = "http://vllm-test:8000/v1"

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_embedder(monkeypatch):
    """Replace QueryEmbedder.get() so no model is loaded during tests."""
    import app.embed_client as ec
    fake = MagicMock()
    fake.encode.return_value = [0.1] * 1024
    monkeypatch.setattr(ec.QueryEmbedder, "get", staticmethod(lambda: fake))
    return fake


@pytest.fixture()
def fake_generate():
    """Async generator that yields a fixed token sequence."""
    async def _gen(messages, max_tokens=1024):
        for tok in ["Hello", " ", "world"]:
            yield tok
    return _gen
