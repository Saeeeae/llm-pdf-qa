import os
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    import redis.asyncio as aioredis
    _redis_available = True
except ImportError:
    _redis_available = False

GLOBAL_LIMIT = 300   # req/min per user/IP
CHAT_LIMIT = 60      # req/min for /api/v1/chat
WEB_SEARCH_LIMIT = 30  # req/min for /api/v1/web-search/*
WINDOW = 60          # seconds (sliding window)


def _redis_client():
    if not _redis_available:
        return None
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        return aioredis.from_url(url, decode_responses=True)
    except Exception:
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user = getattr(request.state, "user", None)
        identity = user.get("sub") if user else request.client.host if request.client else "anon"

        if request.url.path == "/api/v1/chat":
            limit = CHAT_LIMIT
        elif request.url.path.startswith("/api/v1/web-search"):
            limit = WEB_SEARCH_LIMIT
        else:
            limit = GLOBAL_LIMIT
        key = f"rl:{request.url.path}:{identity}"

        r = _redis_client()
        if r:
            try:
                now = time.time()
                window_start = now - WINDOW
                pipe = r.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, WINDOW + 1)
                results = await pipe.execute()
                count = results[2]
                remaining = max(0, limit - count)
                reset = int(now) + WINDOW
                await r.aclose()

                if count > limit:
                    return JSONResponse(
                        {"detail": "Rate limit exceeded"},
                        status_code=429,
                        headers={
                            "X-RateLimit-Limit": str(limit),
                            "X-RateLimit-Remaining": "0",
                            "X-RateLimit-Reset": str(reset),
                        },
                    )

                response = await call_next(request)
                response.headers["X-RateLimit-Limit"] = str(limit)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(reset)
                return response
            except Exception:
                pass

        return await call_next(request)
