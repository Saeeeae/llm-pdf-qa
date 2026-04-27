import pytest
from unittest.mock import AsyncMock, patch, MagicMock

pytestmark = pytest.mark.asyncio


async def test_rate_limit_exceeded(client):
    """When Redis returns count > limit, middleware returns 429."""
    from .conftest import make_token
    token = make_token()

    # Patch _redis_client to return a mock that reports over-limit
    with patch("app.middleware.ratelimit._redis_client") as mock_factory:
        mock_r = AsyncMock()
        # pipeline().execute() returns [None, 1, 999, None] — count=999 > limit
        mock_pipe = AsyncMock()
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)
        mock_pipe.execute = AsyncMock(return_value=[None, 1, 999, None])
        mock_pipe.zremrangebyscore = AsyncMock()
        mock_pipe.zadd = AsyncMock()
        mock_pipe.zcard = AsyncMock()
        mock_pipe.expire = AsyncMock()
        mock_r.pipeline = MagicMock(return_value=mock_pipe)
        mock_r.aclose = AsyncMock()
        mock_factory.return_value = mock_r

        r = await client.get(
            "/api/v1/rag/query",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r.status_code == 429
    assert "X-RateLimit-Limit" in r.headers
    assert r.headers["X-RateLimit-Remaining"] == "0"


async def test_rate_limit_headers_present(client):
    """Normal requests carry rate limit headers when Redis responds."""
    from .conftest import make_token
    token = make_token()
    import httpx

    with patch("app.middleware.ratelimit._redis_client") as mock_factory:
        mock_r = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)
        mock_pipe.execute = AsyncMock(return_value=[None, 1, 5, None])
        mock_pipe.zremrangebyscore = AsyncMock()
        mock_pipe.zadd = AsyncMock()
        mock_pipe.zcard = AsyncMock()
        mock_pipe.expire = AsyncMock()
        mock_r.pipeline = MagicMock(return_value=mock_pipe)
        mock_r.aclose = AsyncMock()
        mock_factory.return_value = mock_r

        with patch("app.clients.downstream.get_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=httpx.Response(200, json={}))
            mock_get.return_value = mock_client
            r = await client.get(
                "/api/v1/rag/query",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert "X-RateLimit-Limit" in r.headers
