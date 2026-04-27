"""APScheduler-based periodic MySQL sync with Redis lock."""
import logging
import os
from datetime import datetime, timezone

import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

_LOCK_KEY = "m1:sync:lock"
_LOCK_TTL = 1800  # 30 min — prevents overlap across workers


async def _run_locked_sync():
    """Acquire Redis lock then run sync. Skips if already locked."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    r = aioredis.from_url(redis_url)
    try:
        acquired = await r.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL)
        if not acquired:
            log.info("Sync skipped — another worker holds the lock")
            return
        await _do_sync()
    finally:
        try:
            await r.delete(_LOCK_KEY)
        except Exception:
            pass
        await r.aclose()


async def _do_sync():
    from ..db import AsyncSessionLocal
    from ..models import SyncRun
    from ..sync.mysql_client import MySQLSource, make_mysql_engine
    from ..sync.syncer import run_sync

    started = datetime.now(timezone.utc)
    engine = make_mysql_engine()
    source = MySQLSource(engine)

    async with AsyncSessionLocal() as session:
        run = SyncRun(started_at=started, status="running")
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    status = "success"
    error_text = None
    report = None
    try:
        async with AsyncSessionLocal() as session:
            report = await run_sync(session, source)
            log.info("Sync complete: %s", report.dict())
    except Exception as e:
        status = "error"
        error_text = str(e)
        log.exception("Sync failed")
    finally:
        await engine.dispose()

    async with AsyncSessionLocal() as session:
        from sqlalchemy import update
        from ..models import SyncRun as SR
        await session.execute(
            update(SR).where(SR.id == run_id).values(
                finished_at=datetime.now(timezone.utc),
                status=status,
                report=report.dict() if report else None,
                error=error_text,
            )
        )
        await session.commit()


def start_scheduler() -> AsyncIOScheduler:
    interval = int(os.getenv("MYSQL_SYNC_INTERVAL_MINUTES", "60"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_locked_sync,
        trigger=IntervalTrigger(minutes=interval),
        id="mysql_sync",
        replace_existing=True,
    )
    scheduler.start()
    log.info("MySQL sync scheduler started (interval=%d min)", interval)
    return scheduler
