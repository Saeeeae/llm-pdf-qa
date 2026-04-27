import os
import redis

TTL = 600


def get_redis():
    return redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


def acquire(rel: str, owner: str) -> bool:
    return bool(get_redis().set(f"m2:doc:{rel}:lock", owner, nx=True, ex=TTL))


def release(rel: str, owner: str):
    r = get_redis()
    cur = r.get(f"m2:doc:{rel}:lock")
    if cur == owner:
        r.delete(f"m2:doc:{rel}:lock")
