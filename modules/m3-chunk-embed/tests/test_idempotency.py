"""B2.1 — Idempotency (Redis dedupe) tests using fakeredis."""
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


def _make_mock_redis(set_returns=True):
    """Create a mock Redis client where set() returns set_returns."""
    r = AsyncMock()
    r.set = AsyncMock(return_value=set_returns)
    r.aclose = AsyncMock()
    return r


def test_idempotency_key_header_first_request():
    """First request with X-Idempotency-Key returns 'queued'."""
    from app.main import app

    mock_r = _make_mock_redis(set_returns=True)  # SET NX succeeds

    with patch("app.routers.chunk_embed._get_redis", return_value=mock_r):
        with TestClient(app) as client:
            r = client.post(
                "/chunk-embed",
                json={"doc_id": "doc1", "markdown_path": "/tmp/x.md"},
                headers={"X-Idempotency-Key": "unique-key-123"},
            )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


def test_idempotency_key_header_duplicate():
    """Second request with same X-Idempotency-Key returns 'duplicate'."""
    from app.main import app

    mock_r = _make_mock_redis(set_returns=None)  # SET NX fails (already set)

    with patch("app.routers.chunk_embed._get_redis", return_value=mock_r):
        with TestClient(app) as client:
            r = client.post(
                "/chunk-embed",
                json={"doc_id": "doc1", "markdown_path": "/tmp/x.md"},
                headers={"X-Idempotency-Key": "unique-key-123"},
            )
    assert r.status_code == 200
    assert r.json()["status"] == "duplicate"
    assert r.json()["doc_id"] == "doc1"


def test_idempotency_body_key_first_request():
    """source_hash in body is used as idempotency key when no header present."""
    from app.main import app

    mock_r = _make_mock_redis(set_returns=True)

    with patch("app.routers.chunk_embed._get_redis", return_value=mock_r):
        with TestClient(app) as client:
            r = client.post(
                "/chunk-embed",
                json={"doc_id": "doc2", "markdown_path": "/tmp/x.md", "source_hash": "abc123"},
            )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    # Confirm the correct Redis key was used
    call_args = mock_r.set.call_args
    assert "m3:idem:doc2:abc123" in call_args[0][0]


def test_idempotency_body_key_duplicate():
    """Duplicate detection via body source_hash."""
    from app.main import app

    mock_r = _make_mock_redis(set_returns=None)

    with patch("app.routers.chunk_embed._get_redis", return_value=mock_r):
        with TestClient(app) as client:
            r = client.post(
                "/chunk-embed",
                json={"doc_id": "doc2", "markdown_path": "/tmp/x.md", "source_hash": "abc123"},
            )
    assert r.json()["status"] == "duplicate"


def test_idempotency_redis_unavailable_proceeds():
    """If Redis is None (unavailable), request still proceeds as 'queued'."""
    from app.main import app

    with patch("app.routers.chunk_embed._get_redis", return_value=None):
        with TestClient(app) as client:
            r = client.post(
                "/chunk-embed",
                json={"doc_id": "doc3", "markdown_path": "/tmp/x.md"},
                headers={"X-Idempotency-Key": "some-key"},
            )
    assert r.json()["status"] == "queued"


def test_idempotency_no_key_no_hash_always_queued():
    """Requests without idempotency key/hash are always queued."""
    from app.main import app

    with TestClient(app) as client:
        r = client.post(
            "/chunk-embed",
            json={"doc_id": "doc4", "markdown_path": "/tmp/x.md"},
        )
    assert r.json()["status"] == "queued"
