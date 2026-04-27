from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_chat_web_search_requires_web_permission(client):
    from .conftest import make_token

    token = make_token(perms=["chat.use"])
    r = await client.post(
        "/api/v1/chat",
        json={"message": "p53", "use_web_search": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert "web.search" in r.json()["detail"]


async def test_chat_web_search_passes_flag_to_m4(client):
    from .conftest import make_token

    token = make_token(perms=["chat.use", "web.search"])

    async def fake_aiter():
        yield "ok"

    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=MagicMock(aiter_text=fake_aiter))
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.clients.downstream.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_get.return_value = mock_client
        r = await client.post(
            "/api/v1/chat",
            json={"message": "p53", "session_id": "s1", "use_web_search": True, "web_provider": "curated"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 200
    _, kwargs = mock_client.stream.call_args
    assert kwargs["json"]["use_web"] is True
    assert kwargs["json"]["web_provider"] == "curated"


async def test_web_search_proxy_requires_permission(client):
    from .conftest import make_token

    token = make_token(perms=["chat.use"])
    r = await client.get(
        "/api/v1/web-search/providers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


async def test_web_search_proxy_with_permission(client):
    from .conftest import make_token

    token = make_token(perms=["web.search"])
    mock_resp = httpx.Response(200, json={"providers": []})
    with patch("app.clients.downstream.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_get.return_value = mock_client
        r = await client.get(
            "/api/v1/web-search/providers",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 200
    _, kwargs = mock_client.request.call_args
    assert kwargs["url"] == "http://m8-web-search:8000/web-search/providers"
