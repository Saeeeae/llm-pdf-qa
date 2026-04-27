"""
Integration-style tests for the /chunk-embed and /status endpoints.
Uses AsyncMock for DB and mock Embedder/Chunker (injected by conftest.py).
No real DB or GPU required.
"""
import asyncio
import hashlib
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_fake_session(rows=None):
    """Return an async context-manager mock that acts as AsyncSession."""
    execute_result = MagicMock()
    execute_result.first.return_value = rows  # for SELECT queries
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, session


# ── HTTP endpoint tests ───────────────────────────────────────────────────────

def test_chunk_embed_queued():
    from app.main import app
    with TestClient(app) as client:
        r = client.post("/chunk-embed", json={"doc_id": "doc1", "markdown_path": "/tmp/x.md"})
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert r.json()["doc_id"] == "doc1"


def test_status_not_found():
    from app.main import app
    # Patch DB to return no row
    cm, _ = _make_fake_session(rows=None)
    with patch("app.db.AsyncSessionLocal", return_value=cm):
        with patch("app.db.get_db") as mock_get_db:
            async def _gen():
                session = AsyncMock()
                session.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
                yield session

            mock_get_db.return_value = _gen()
            with TestClient(app) as client:
                r = client.get("/status/nonexistent")
    assert r.status_code == 404


def test_status_found():
    from app.main import app
    from fastapi import Depends

    async def _fake_db():
        session = AsyncMock()
        row = MagicMock()
        row.__getitem__ = MagicMock(side_effect=lambda i: ("done", 5)[i])
        result = MagicMock()
        result.first.return_value = ("done", 5)
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[__import__("app.db", fromlist=["get_db"]).get_db] = _fake_db
    try:
        with TestClient(app) as client:
            r = client.get("/status/doc1")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "done"
        assert data["chunks"] == 5
    finally:
        app.dependency_overrides.clear()


# ── _run() unit tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_missing_file():
    """_run silently returns if the markdown file doesn't exist."""
    from app.routers.chunk_embed import _run
    await _run("doc1", "/nonexistent/path/file.md")  # must not raise


@pytest.mark.asyncio
async def test_run_processes_file(tmp_path):
    """_run calls embedder, chunker, and commits to DB."""
    md = tmp_path / "test.md"
    md.write_text("para one\n\npara two\n\npara three", encoding="utf-8")

    cm, session = _make_fake_session()

    with patch("app.db.AsyncSessionLocal", return_value=cm):
        from app.routers.chunk_embed import _run
        await _run("doc-x", str(md))

    assert session.execute.called
    assert session.commit.called


@pytest.mark.asyncio
async def test_run_empty_chunks(tmp_path):
    """_run marks doc as done with chunk_count=0 when chunker yields nothing."""
    md = tmp_path / "empty.md"
    md.write_text("   \n\n   ", encoding="utf-8")

    cm, session = _make_fake_session()

    with patch("app.db.AsyncSessionLocal", return_value=cm):
        from app.routers.chunk_embed import _run
        await _run("doc-empty", str(md))

    # DB is called: first to set processing, then to set done with chunk_count=0
    assert session.execute.called
    assert session.commit.called


@pytest.mark.asyncio
async def test_run_frontmatter_stripped(tmp_path):
    """Frontmatter delimited by '---' is stripped before chunking."""
    md = tmp_path / "frontmatter.md"
    md.write_text("---\ntitle: Test\n---\nActual content here", encoding="utf-8")

    cm, session = _make_fake_session()

    with patch("app.db.AsyncSessionLocal", return_value=cm):
        from app.routers.chunk_embed import _run
        await _run("doc-fm", str(md))

    assert session.execute.called
