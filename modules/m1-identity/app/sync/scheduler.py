"""APScheduler-based periodic MySQL sync with Redis lock.

After a successful m1 sync (and successfully committed SyncRun row), fires
a fire-and-forget HTTP trigger to m2's internal sync endpoint so downstream
file/ACL ingestion runs against a fresh identity snapshot. Trigger failure
is logged but does not fail m1.
"""
import logging
import os
from datetime import datetime, timezone

import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .notify import trigger_m2

log = logging.getLogger(__name__)

_LOCK_KEY = "m1:sync:lock"
_DEFAULT_LOCK_TTL = 1800  # 30 min — see SYNC_LOCK_TTL_SECONDS env override


def _lock_ttl() -> int:
    return int(os.getenv("SYNC_LOCK_TTL_SECONDS", str(_DEFAULT_LOCK_TTL)))


def _redis_url() -> str:
    # Default targets the in-network redis service, not localhost.
    return os.getenv("REDIS_URL", "redis://redis:6379/0")


async def run_locked_sync() -> None:
    """Acquire Redis lock then run sync. Skips if already locked.

    Public entry point used by the APScheduler job and the on-startup hook.
    """
    r = aioredis.from_url(_redis_url())
    try:
        acquired = await r.set(_LOCK_KEY, "1", nx=True, ex=_lock_ttl())
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


# Backwards-compat alias for tests/imports that still use the underscored name
_run_locked_sync = run_locked_sync


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

    # Persist final SyncRun status BEFORE triggering m2: if the row update
    # fails (DB blip), we don't want to tell m2 that m1 succeeded.
    update_committed = False
    try:
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
            update_committed = True
    except Exception:
        log.exception("Failed to persist SyncRun final status")

    if status == "success" and update_committed:
        await trigger_m2()


def start_scheduler() -> AsyncIOScheduler:
    interval = int(os.getenv("MYSQL_SYNC_INTERVAL_MINUTES", "60"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_locked_sync,
        trigger=IntervalTrigger(minutes=interval),
        id="mysql_sync",
        replace_existing=True,
    )
    scheduler.start()
    log.info("MySQL sync scheduler started (interval=%d min)", interval)
    return scheduler
