import os
import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from rag_shared.logging import setup_logging

from .db import get_db, init_db
from .middleware import RequestIDMiddleware
from .routers import auth, users
from .routers import sync as sync_router

setup_logging("m1-identity")

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    if os.getenv("TEST_MODE", "0") == "1":
        await init_db()
    else:
        from .sync.scheduler import start_scheduler, _run_locked_sync
        _scheduler = start_scheduler()
        if os.getenv("MYSQL_SYNC_ON_STARTUP", "0") == "1":
            import asyncio
            asyncio.ensure_future(_run_locked_sync())
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="M1 Identity", version="1.0.0", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sync_router.router)


@app.get("/health")
def health():
    return {"status": "ok", "module": "m1-identity"}


@app.get("/ready")
async def ready():
    errors = []
    # Check DB
    try:
        from sqlalchemy import text
        from .db import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        errors.append(f"db: {e}")

    # Check Redis
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = aioredis.from_url(redis_url)
        await r.ping()
        await r.aclose()
    except Exception as e:
        errors.append(f"redis: {e}")

    if errors:
        # Returning a tuple makes FastAPI serialize it as a 200 list. Use
        # JSONResponse so orchestrators see the actual 503.
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "errors": errors},
        )
    return {"status": "ok"}
