import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


async def test_login_success(ctx):
    client, session, user, role = ctx
    r = await client.post("/auth/login", json={"email": "admin@test.com", "password": "correct-password"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(ctx):
    client, session, user, role = ctx
    r = await client.post("/auth/login", json={"email": "admin@test.com", "password": "wrong"})
    assert r.status_code == 401


async def test_login_unknown_user(ctx):
    client, session, user, role = ctx
    r = await client.post("/auth/login", json={"email": "nobody@test.com", "password": "x"})
    assert r.status_code == 401


async def test_login_lockout_after_5_fails(ctx):
    """After 5 failures Redis counter triggers 429."""
    client, session, user, role = ctx
    LOCKOUT_FAILS = 5

    with patch("app.routers.auth._redis") as mock_redis_factory:
        mock_r = AsyncMock()
        mock_redis_factory.return_value = mock_r

        for i in range(5):
            mock_r.get.return_value = str(i) if i > 0 else None
            r = await client.post("/auth/login", json={"email": "admin@test.com", "password": "wrong"})
            assert r.status_code == 401

        # 6th call: counter >= 5 → locked
        mock_r.get.return_value = "5"
        mock_r.ttl.return_value = 900
        r = await client.post("/auth/login", json={"email": "admin@test.com", "password": "wrong"})
        assert r.status_code == 429
        assert "Retry-After" in r.headers
