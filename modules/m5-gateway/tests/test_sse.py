import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


async def test_chat_requires_auth(client):
    r = await client.post("/api/v1/chat", json={"message": "hello"})
    assert r.status_code == 401


async def test_chat_requires_chat_perm(client):
    from .conftest import make_token
    # Token with no chat.use
    token = make_token(perms=["doc.read"])
    r = await client.post(
        "/api/v1/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


async def test_chat_streams_sse(client):
    from .conftest import make_token
    token = make_token(perms=["chat.use"])

    # m5 does a transparent pass-through of m4's SSE bytes — it must NOT
    # re-wrap event types. We feed pre-framed SSE upstream and assert the
    # same framing emerges from the gateway.
    async def fake_aiter_bytes():
        yield b"event: token\ndata: {\"token\": \"hello\", \"delta\": \"hello\"}\n\n"
        yield b"event: token\ndata: {\"token\": \" world\", \"delta\": \" world\"}\n\n"
        yield b"event: done\ndata: {}\n\n"

    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(
        return_value=MagicMock(aiter_bytes=fake_aiter_bytes)
    )
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.clients.downstream.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_get.return_value = mock_client

        r = await client.post(
            "/api/v1/chat",
            json={"message": "hello", "session_id": "s1"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    body = r.text
    assert "event: token" in body
    assert "delta" in body
    assert "event: done" in body
