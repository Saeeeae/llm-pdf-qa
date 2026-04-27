"""test_metrics_cache.py — Redis cache hit/miss for metrics endpoints."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_value():
    """cache_get should return parsed dict on hit."""
    import json
    from app.cache import cache_get, cache_set

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps({"utilization_pct": 42.0}))
    mock_redis.set = AsyncMock()

    with patch("app.cache.get_redis", return_value=mock_redis):
        result = await cache_get("metrics:gpu")
        assert result == {"utilization_pct": 42.0}


@pytest.mark.asyncio
async def test_cache_miss_returns_none():
    """cache_get returns None when key not in Redis."""
    from app.cache import cache_get

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("app.cache.get_redis", return_value=mock_redis):
        result = await cache_get("metrics:gpu")
        assert result is None


@pytest.mark.asyncio
async def test_cache_set_stores_json():
    """cache_set serializes value as JSON with TTL."""
    import json
    from app.cache import cache_set

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()

    data = {"cpu_pct": 10.5}
    with patch("app.cache.get_redis", return_value=mock_redis):
        await cache_set("metrics:server", data, ttl=30)
        mock_redis.set.assert_called_once_with("metrics:server", json.dumps(data), ex=30)


@pytest.mark.asyncio
async def test_cache_error_does_not_raise():
    """Redis errors are swallowed silently (cache is best-effort)."""
    from app.cache import cache_get, cache_set

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("redis down"))
    mock_redis.set = AsyncMock(side_effect=ConnectionError("redis down"))

    with patch("app.cache.get_redis", return_value=mock_redis):
        result = await cache_get("metrics:gpu")
        assert result is None  # no exception raised

        await cache_set("metrics:gpu", {"x": 1})  # no exception raised
