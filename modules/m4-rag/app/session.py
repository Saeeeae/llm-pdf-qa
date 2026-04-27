import json
import os

TTL = int(os.getenv("SESSION_TTL", "3600"))
MAX_TURNS = 5


def _redis():
    import redis.asyncio as aredis
    return aredis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


async def get_history(session_id: str) -> list[dict]:
    r = _redis()
    try:
        raw = await r.lrange(f"m4:sess:{session_id}", 0, MAX_TURNS * 2 - 1)
        return [json.loads(x) for x in raw][::-1]
    finally:
        await r.aclose()


async def add_turn(session_id: str, user: str, assistant: str) -> None:
    r = _redis()
    try:
        key = f"m4:sess:{session_id}"
        pipe = r.pipeline()
        pipe.lpush(key, json.dumps({"role": "assistant", "content": assistant}))
        pipe.lpush(key, json.dumps({"role": "user", "content": user}))
        pipe.ltrim(key, 0, MAX_TURNS * 2 - 1)
        pipe.expire(key, TTL)
        await pipe.execute()
    finally:
        await r.aclose()
