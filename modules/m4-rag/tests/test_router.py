"""Router tests — TestClient with monkeypatched LLM client and retriever."""
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _fake_sources():
    return [
        {
            "id": 1,
            "doc_id": "doc1",
            "chunk_idx": 0,
            "text": "Test context text.",
            "metadata": {},
            "rrf": 0.032,
        }
    ]


async def _fake_generate(messages, max_tokens=1024):
    for tok in ["Answer", " here"]:
        yield tok


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_query_non_stream(monkeypatch):
    monkeypatch.setattr("app.routers.rag.hybrid_search", AsyncMock(return_value=_fake_sources()))
    monkeypatch.setattr("app.routers.rag.generate_stream", _fake_generate)

    r = client.post("/rag/query", json={"query": "test question"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "Answer here"
    assert len(data["sources"]) == 1
    assert data["sources"][0]["doc_id"] == "doc1"


def test_query_non_stream_score(monkeypatch):
    monkeypatch.setattr("app.routers.rag.hybrid_search", AsyncMock(return_value=_fake_sources()))
    monkeypatch.setattr("app.routers.rag.generate_stream", _fake_generate)

    r = client.post("/rag/query", json={"query": "test"})
    data = r.json()
    assert isinstance(data["sources"][0]["score"], float)


def test_query_stream(monkeypatch):
    monkeypatch.setattr("app.routers.rag.hybrid_search", AsyncMock(return_value=_fake_sources()))
    monkeypatch.setattr("app.routers.rag.generate_stream", _fake_generate)

    r = client.post("/rag/query?stream=1", json={"query": "stream test"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    body = r.text
    assert "event: sources" in body
    assert "event: token" in body
    assert "event: done" in body


def test_query_empty_sources(monkeypatch):
    monkeypatch.setattr("app.routers.rag.hybrid_search", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.routers.rag.generate_stream", _fake_generate)

    r = client.post("/rag/query", json={"query": "nothing"})
    assert r.status_code == 200
    assert r.json()["sources"] == []


def test_query_top_k_passed(monkeypatch):
    mock_search = AsyncMock(return_value=[])
    monkeypatch.setattr("app.routers.rag.hybrid_search", mock_search)
    monkeypatch.setattr("app.routers.rag.generate_stream", _fake_generate)

    client.post("/rag/query", json={"query": "q", "top_k": 3})
    _, kwargs = mock_search.call_args
    assert mock_search.call_args[1].get("k") == 3 or mock_search.call_args[0][3] == 3
