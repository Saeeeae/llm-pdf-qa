"""
Previous web-search stub tests — replaced by test_router.py.

M4 no longer calls M8 directly; web-search routing is handled by M5 gateway.
These tests verify the new contract: /rag/query returns `answer` + `sources`,
with no `web_search` key, and the LLM client is used via generate_stream.
"""
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


async def _fake_gen(messages, max_tokens=1024):
    yield "ok"


def test_query_returns_answer_and_sources(monkeypatch):
    monkeypatch.setattr("app.routers.rag.hybrid_search", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.routers.rag.generate_stream", _fake_gen)

    r = client.post("/rag/query", json={"query": "hello"})
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert "sources" in data
    assert "web_search" not in data


def test_query_no_web_field_in_request_model(monkeypatch):
    """use_web is no longer a valid field — extra fields are ignored by Pydantic."""
    monkeypatch.setattr("app.routers.rag.hybrid_search", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.routers.rag.generate_stream", _fake_gen)

    r = client.post("/rag/query", json={"query": "p53", "use_web": True})
    assert r.status_code == 200
    assert "web_search" not in r.json()


def test_query_llm_called(monkeypatch):
    """generate_stream must be invoked for every query."""
    mock_search = AsyncMock(return_value=[])
    called = []

    async def _counting_gen(messages, max_tokens=1024):
        called.append(1)
        yield "result"

    monkeypatch.setattr("app.routers.rag.hybrid_search", mock_search)
    monkeypatch.setattr("app.routers.rag.generate_stream", _counting_gen)

    client.post("/rag/query", json={"query": "test"})
    assert len(called) == 1
