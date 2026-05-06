import os
import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from fastapi import FastAPI
from rag_shared.logging import setup_logging

from .admin_bootstrap import maybe_bootstrap_admin
from .db import get_db, init_db
from .middleware import RequestIDMiddleware
from .routers import admin, auth, users
from .routers import sync as sync_router

# LOG_FILE_PATH env enables a rotating file handler in addition to stdout.
# In docker, this path is bind-mounted to the host's data/logs/m1-identity/.
setup_logging("m1-identity", log_file=os.getenv("LOG_FILE_PATH"))

_scheduler = None
_startup_sync_task = None  # tracked so lifespan can cancel it cleanly


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler, _startup_sync_task
    if os.getenv("TEST_MODE", "0") == "1":
        await init_db()
    # Auto-bootstrap an admin user when env is set and no admin exists yet.
    # Idempotent so re-deploys are safe; errors are logged not raised.
    await maybe_bootstrap_admin()
    if os.getenv("TEST_MODE", "0") != "1":
        from .sync.scheduler import run_locked_sync, start_scheduler
        _scheduler = start_scheduler()
        if os.getenv("MYSQL_SYNC_ON_STARTUP", "0") == "1":
            import asyncio
            _startup_sync_task = asyncio.create_task(run_locked_sync())
    yield
    if _startup_sync_task and not _startup_sync_task.done():
        _startup_sync_task.cancel()
        try:
            await _startup_sync_task
        except (Exception, BaseException):
            pass
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="M1 Identity", version="1.0.0", lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sync_router.router)
app.include_router(admin.router)


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
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = aioredis.from_url(redis_url)
        await r.ping()
        await r.aclose()
    except Exception as e:
        errors.append(f"redis: {e}")

    if errors:
        return {"status": "degraded", "errors": errors}, 503
    return {"status": "ok"}
