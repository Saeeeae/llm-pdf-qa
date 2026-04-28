"""Conversation session storage in Redis.

Uses a shared `redis.asyncio` connection pool — one per worker — instead of
opening a fresh connection per call. The pool lives for the process lifetime
and is closed via `aclose_pool()` from the FastAPI lifespan handler.
"""
from __future__ import annotations

import json
import os

TTL = int(os.getenv("SESSION_TTL", "3600"))
MAX_TURNS = 5
MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))

_pool = None  # redis.asyncio.ConnectionPool


def _client():
    """Lazily build a shared connection pool, return a Redis client wrapping it."""
    global _pool
    import redis.asyncio as aredis
    if _pool is None:
        _pool = aredis.ConnectionPool.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
            max_connections=MAX_CONNECTIONS,
        )
    return aredis.Redis(connection_pool=_pool)


async def aclose_pool() -> None:
    """Close pool on shutdown — idempotent."""
    global _pool
    if _pool is not None:
        await _pool.disconnect(inuse_connections=True)
        _pool = None


async def get_history(session_id: str) -> list[dict]:
    r = _client()
    raw = await r.lrange(f"m4:sess:{session_id}", 0, MAX_TURNS * 2 - 1)
    return [json.loads(x) for x in raw][::-1]


async def add_turn(session_id: str, user: str, assistant: str) -> None:
    r = _client()
    key = f"m4:sess:{session_id}"
    pipe = r.pipeline()
    pipe.lpush(key, json.dumps({"role": "assistant", "content": assistant}))
    pipe.lpush(key, json.dumps({"role": "user", "content": user}))
    pipe.ltrim(key, 0, MAX_TURNS * 2 - 1)
    pipe.expire(key, TTL)
    await pipe.execute()
