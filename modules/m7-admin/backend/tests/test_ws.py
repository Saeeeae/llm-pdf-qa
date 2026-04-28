"""test_ws.py — WebSocket admin events endpoint."""
import json
import os
# Production default disables `?token=` query-param auth (token leaks to access
# logs). The TestClient's websocket_connect can't easily set the Authorization
# header, so we opt-in to query-param auth for the test suite only.
os.environ.setdefault("WS_ALLOW_QUERY_TOKEN", "1")

from datetime import datetime, timedelta, timezone  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from jose import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def _admin_token() -> str:
    return jwt.encode(
        {
            "sub": "admin-1",
            "permissions": ["admin.read", "admin.write"],
            "perm": ["admin.read", "admin.write"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


def _make_mock_pubsub(messages: list[dict]):
    """Create a mock Redis pubsub that yields the given messages then stops."""
    async def _listen():
        for msg in messages:
            yield msg

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()
    pubsub.listen = _listen
    return pubsub


def _make_mock_redis(pubsub):
    mock_redis = MagicMock()
    mock_redis.pubsub = MagicMock(return_value=pubsub)
    mock_redis.aclose = AsyncMock()
    return mock_redis


def test_ws_endpoint_accepts_connection():
    """WebSocket /admin/ws accepts connections with valid admin token."""
    mock_msg = {
        "type": "message",
        "channel": "audit_events",
        "data": json.dumps({"action": "chat.query", "user_id": "u1"}),
    }
    pubsub = _make_mock_pubsub([mock_msg])
    mock_redis = _make_mock_redis(pubsub)

    token = _admin_token()
    with patch("app.routers.ws.aioredis.from_url", return_value=mock_redis):
        client = TestClient(app)
        with client.websocket_connect(f"/admin/ws?token={token}") as ws:
            data = ws.receive_json()
            assert data["channel"] == "audit_events"
            assert data["data"]["action"] == "chat.query"


def test_ws_ignores_non_message_events():
    """Subscribe/psubscribe confirmation messages are ignored."""
    messages = [
        {"type": "subscribe", "channel": "audit_events", "data": 1},
        {
            "type": "message",
            "channel": "pipeline_events",
            "data": json.dumps({"status": "done"}),
        },
    ]
    pubsub = _make_mock_pubsub(messages)
    mock_redis = _make_mock_redis(pubsub)

    token = _admin_token()
    with patch("app.routers.ws.aioredis.from_url", return_value=mock_redis):
        client = TestClient(app)
        with client.websocket_connect(f"/admin/ws?token={token}") as ws:
            data = ws.receive_json()
            assert data["channel"] == "pipeline_events"


def test_ws_rejects_no_token():
    """WebSocket /admin/ws rejects connections without token."""
    client = TestClient(app)
    with pytest.raises(Exception):  # WebSocketDisconnect with code 1008
        with client.websocket_connect("/admin/ws"):
            pass


def test_ws_rejects_invalid_token():
    """WebSocket /admin/ws rejects connections with invalid token."""
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/admin/ws?token=invalid.token.here"):
            pass
