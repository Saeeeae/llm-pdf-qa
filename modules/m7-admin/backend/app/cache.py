"""
cache.py — Redis client for M7 admin backend.
Used to cache expensive metrics (GPU, chunking stats) with short TTLs.
"""
import os
import json
from typing import Any, Optional
import redis.asyncio as aioredis

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_pool: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(_REDIS_URL, decode_responses=True)
    return _pool


async def cache_get(key: str) -> Optional[Any]:
    try:
        r = get_redis()
        val = await r.get(key)
        return json.loads(val) if val is not None else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = 30) -> None:
    try:
        r = get_redis()
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass  # cache miss on Redis errors is acceptable


async def check_redis_connectivity() -> bool:
    try:
        r = get_redis()
        # redis.asyncio.Redis.ping() is typed as Awaitable[bool] | bool depending
        # on redis-py version; cast through Any so mypy doesn't trip on the union.
        await r.ping()  # type: ignore[misc]
        return True
    except Exception:
        return False
