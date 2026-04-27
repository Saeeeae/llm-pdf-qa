"""Admin endpoints for MySQL sync management."""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.rbac import Permission, require
from ..db import get_db
from ..models import SyncRun

router = APIRouter(prefix="/admin/sync/mysql", tags=["sync"])

_last_triggered_run_id: list[int] = []  # simple in-process store


@router.post("", status_code=202)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require(Permission.admin_write)),
):
    """Trigger a full MySQL sync in the background. Returns 202 + run_id."""
    run = SyncRun(started_at=datetime.now(timezone.utc), status="queued")
    db.add(run)
    await db.commit()
    await db.refresh(run)
    _last_triggered_run_id.clear()
    _last_triggered_run_id.append(run.id)

    background_tasks.add_task(_bg_sync, run.id)
    return {"status": "accepted", "run_id": run.id}


async def _bg_sync(run_id: int):
    import logging
    import os
    from sqlalchemy import update
    from ..db import AsyncSessionLocal
    from ..models import SyncRun as SR
    from ..sync.mysql_client import MySQLSource, make_mysql_engine
    from ..sync.syncer import run_sync

    log = logging.getLogger(__name__)
    engine = make_mysql_engine()
    source = MySQLSource(engine)
    status = "success"
    error_text = None
    report = None
    try:
        async with AsyncSessionLocal() as session:
            report = await run_sync(session, source)
    except Exception as e:
        status = "error"
        error_text = str(e)
        log.exception("Background sync failed")
    finally:
        await engine.dispose()

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(SR).where(SR.id == run_id).values(
                finished_at=datetime.now(timezone.utc),
                status=status,
                report=report.dict() if report else None,
                error=error_text,
            )
        )
        await session.commit()


@router.get("/status")
async def sync_status(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require(Permission.admin_read)),
):
    """Last sync run report + next scheduled run time."""
    import os
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    result = await db.execute(select(SyncRun).order_by(desc(SyncRun.started_at)).limit(1))
    last = result.scalar_one_or_none()

    interval = int(os.getenv("MYSQL_SYNC_INTERVAL_MINUTES", "60"))
    return {
        "last_run": _run_to_dict(last) if last else None,
        "sync_interval_minutes": interval,
    }


@router.get("/history")
async def sync_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require(Permission.audit_read)),
):
    """Recent sync run history."""
    result = await db.execute(
        select(SyncRun).order_by(desc(SyncRun.started_at)).limit(min(limit, 200))
    )
    runs = result.scalars().all()
    return [_run_to_dict(r) for r in runs]


def _run_to_dict(run: SyncRun) -> dict:
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "report": run.report,
        "error": run.error,
    }
