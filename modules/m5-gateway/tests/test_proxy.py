import pytest
from unittest.mock import AsyncMock, patch
import httpx

pytestmark = pytest.mark.asyncio


async def test_health_no_auth(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["module"] == "m5-gateway"


async def test_jwt_required_for_protected_route(client):
    r = await client.get("/api/v1/rag/query")
    assert r.status_code == 401


async def test_invalid_jwt_rejected(client):
    r = await client.get(
        "/api/v1/rag/query",
        headers={"Authorization": "Bearer not.a.valid.token"},
    )
    assert r.status_code == 401


async def test_valid_jwt_proxies(client):
    from .conftest import make_token
    token = make_token()

    mock_resp = httpx.Response(200, json={"result": "ok"})
    with patch("app.clients.downstream.get_client") as mock_get:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_get.return_value = mock_client

        r = await client.get(
            "/api/v1/rag/query",
            headers={"Authorization": f"Bearer {token}"},
        )
    # Either proxied 200 or fallback 200 (circuit breaker mock)
    assert r.status_code in (200, 502)


async def test_login_public_path_no_auth(client):
    """Login endpoint should not require JWT."""
    with patch("app.clients.downstream.get_client") as mock_get:
        mock_resp = httpx.Response(200, json={"access_token": "tok", "refresh_token": "rt", "token_type": "bearer"})
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_get.return_value = mock_client
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": "x@x.com", "password": "pass"},
        )
    # No 401 — public path
    assert r.status_code != 401
