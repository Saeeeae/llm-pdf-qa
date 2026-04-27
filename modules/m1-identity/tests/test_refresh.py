import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


async def test_refresh_rotation(ctx):
    client, session, user, role = ctx

    with patch("app.routers.auth._redis") as mock_redis_factory:
        mock_r = AsyncMock()
        mock_r.get.return_value = None
        mock_redis_factory.return_value = mock_r
        r = await client.post("/auth/login", json={"email": "admin@test.com", "password": "correct-password"})
    assert r.status_code == 200
    old_refresh = r.json()["refresh_token"]

    r2 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 200
    data = r2.json()
    assert "access_token" in data
    new_refresh = data["refresh_token"]
    assert new_refresh != old_refresh


async def test_refresh_replay_detection(ctx):
    """Replaying a used refresh token should return 401 with theft detection message."""
    client, session, user, role = ctx

    with patch("app.routers.auth._redis") as mock_redis_factory:
        mock_r = AsyncMock()
        mock_r.get.return_value = None
        mock_redis_factory.return_value = mock_r
        r = await client.post("/auth/login", json={"email": "admin@test.com", "password": "correct-password"})
    old_refresh = r.json()["refresh_token"]

    # First use: OK
    r2 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 200

    # Replay: must be 401
    r3 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r3.status_code == 401
    detail = r3.json()["detail"].lower()
    assert "reuse" in detail or "theft" in detail


async def test_refresh_invalid_token(ctx):
    client, *_ = ctx
    r = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert r.status_code == 401
