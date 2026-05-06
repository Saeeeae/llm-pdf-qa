"""Admin operational endpoints — runtime visibility for operators.

These complement /admin/sync/mysql/status (sync-specific) with a broader
identity-data view: row counts per table, role distribution, and the most
recent sync run summary.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.rbac import Permission, require
from ..db import get_db
from ..models import Department, Role, SyncRun, User

router = APIRouter(prefix="/admin", tags=["admin"])


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Treat naive datetimes as UTC (SQLite returns naive even when stored aware)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _sync_run_summary(run: SyncRun) -> dict[str, Any]:
    finished_at = _as_utc(run.finished_at)
    started_at = _as_utc(run.started_at)
    finished = finished_at.isoformat() if finished_at else None
    started = started_at.isoformat() if started_at else None
    age_seconds: Optional[float] = None
    if finished_at:
        age_seconds = (datetime.now(timezone.utc) - finished_at).total_seconds()
    return {
        "id": run.id,
        "status": run.status,
        "started_at": started,
        "finished_at": finished,
        "age_seconds": age_seconds,
        "report": run.report,
        "error": run.error,
    }


@router.get("/health")
async def admin_health(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require(Permission.admin_read)),
):
    """Operational snapshot: row counts + last sync.

    Useful for "did the bootstrap fire?" / "is sync still landing?" without
    needing direct DB access. RBAC-gated (admin.read).
    """
    users_total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    users_active = (
        await db.execute(
            select(func.count(User.id)).where(User.is_active == True)  # noqa: E712
        )
    ).scalar() or 0
    roles_total = (await db.execute(select(func.count(Role.id)))).scalar() or 0
    departments_total = (
        await db.execute(select(func.count(Department.id)))
    ).scalar() or 0

    by_role_rows = (
        await db.execute(
            select(Role.name, func.count(User.id))
            .join(User, User.role_id == Role.id, isouter=True)
            .group_by(Role.name)
        )
    ).all()
    users_by_role = {name: int(count) for name, count in by_role_rows}

    last_run_row = await db.execute(
        select(SyncRun).order_by(desc(SyncRun.started_at)).limit(1)
    )
    last_run = last_run_row.scalar_one_or_none()

    return {
        "users": {
            "total": int(users_total),
            "active": int(users_active),
            "by_role": users_by_role,
        },
        "roles": {"total": int(roles_total)},
        "departments": {"total": int(departments_total)},
        "last_sync_run": _sync_run_summary(last_run) if last_run else None,
    }
