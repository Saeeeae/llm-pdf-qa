import json
import time

from .lock import get_redis

KEY = "m2:dlq"


def push(entry: dict):
    get_redis().lpush(KEY, json.dumps({**entry, "ts": time.time()}))


def pop_eligible(now: float, max_n: int = 100) -> list[dict]:
    r = get_redis()
    out, requeue = [], []
    for _ in range(min(r.llen(KEY), max_n)):
        raw = r.rpop(KEY)
        if raw is None:
            break
        e = json.loads(raw)
        if e.get("next_retry", 0) <= now and e.get("retry_count", 0) < 3:
            out.append(e)
        else:
            requeue.append(raw)
    for raw in requeue:
        r.lpush(KEY, raw)
    return out
