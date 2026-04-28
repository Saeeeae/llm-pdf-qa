"""MySQL → Postgres batch sync logic."""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .source_rows import SourceDepartment, SourceRole, SourceUser

log = logging.getLogger(__name__)


@dataclass
class SyncReport:
    roles_added: int = 0
    roles_updated: int = 0
    departments_added: int = 0
    departments_updated: int = 0
    users_added: int = 0
    users_updated: int = 0
    users_deactivated: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def dict(self) -> dict:
        return {
            "roles_added": self.roles_added,
            "roles_updated": self.roles_updated,
            "departments_added": self.departments_added,
            "departments_updated": self.departments_updated,
            "users_added": self.users_added,
            "users_updated": self.users_updated,
            "users_deactivated": self.users_deactivated,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }


def _json_safe(v: Any) -> Any:
    """Ensure permissions is a Python list (MySQL may return str)."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


async def _sync_roles(session: AsyncSession, source) -> tuple[int, int]:
    from ..models import Role
    rows = await source.fetch_roles()
    added = updated = 0
    for row in rows:
        src = SourceRole.from_row(row)
        result = await session.execute(select(Role).where(Role.external_id == src.external_id))
        role = result.scalar_one_or_none()
        if role is None:
            result2 = await session.execute(select(Role).where(Role.name == src.name))
            role = result2.scalar_one_or_none()
        perms = _json_safe(src.permissions)
        if role is None:
            session.add(Role(
                external_id=src.external_id,
                name=src.name,
                permissions=perms,
                description=src.description,
            ))
            added += 1
        else:
            role.external_id = src.external_id
            role.name = src.name
            role.permissions = perms
            role.description = src.description
            updated += 1
    await session.flush()
    return added, updated


async def _sync_departments(session: AsyncSession, source) -> tuple[int, int]:
    from ..models import Department
    rows = await source.fetch_departments()
    srcs = [SourceDepartment.from_row(r) for r in rows]
    added = updated = 0

    # First pass: upsert without parent (avoids FK circular issues)
    for src in srcs:
        result = await session.execute(
            select(Department).where(Department.external_id == src.external_id)
        )
        dept = result.scalar_one_or_none()
        if dept is None:
            session.add(Department(external_id=src.external_id, name=src.name, parent_id=None))
            added += 1
        else:
            dept.name = src.name
            updated += 1
    await session.flush()

    # Second pass: set parent_id
    for src in srcs:
        if src.parent_external_id is None:
            continue
        result = await session.execute(
            select(Department).where(Department.external_id == src.external_id)
        )
        dept = result.scalar_one_or_none()
        parent_result = await session.execute(
            select(Department).where(Department.external_id == src.parent_external_id)
        )
        parent = parent_result.scalar_one_or_none()
        if dept and parent:
            dept.parent_id = parent.id
    await session.flush()
    return added, updated


async def _sync_users(session: AsyncSession, source) -> tuple[int, int, int]:
    from ..models import Department, Role, User
    now = datetime.now(timezone.utc)
    seen_external_ids: set[int] = set()
    added = updated = 0

    # Build lookup caches
    role_map: dict[int, int] = {}  # external_id -> local id
    dept_map: dict[int, int] = {}

    role_rows = (await session.execute(select(Role.external_id, Role.id).where(Role.external_id.isnot(None)))).all()
    for ext_id, local_id in role_rows:
        role_map[ext_id] = local_id

    dept_rows = (await session.execute(select(Department.external_id, Department.id).where(Department.external_id.isnot(None)))).all()
    for ext_id, local_id in dept_rows:
        dept_map[ext_id] = local_id

    async for batch in source.fetch_users():
        for row in batch:
            src = SourceUser.from_row(row)
            seen_external_ids.add(src.external_id)

            role_id = role_map.get(src.role_external_id) if src.role_external_id else None
            dept_id = dept_map.get(src.department_external_id) if src.department_external_id else None

            result = await session.execute(select(User).where(User.email == src.email))
            user = result.scalar_one_or_none()

            if user is None:
                session.add(User(
                    email=src.email,
                    name=src.name or src.email,
                    password_hash=src.password_hash or "",
                    external_id=src.external_id,
                    is_active=src.is_active,
                    role_id=role_id,
                    department_id=dept_id,
                    last_synced_at=now,
                ))
                added += 1
            else:
                user.name = src.name or user.name
                user.is_active = src.is_active
                user.role_id = role_id
                user.department_id = dept_id
                user.external_id = src.external_id
                if src.password_hash:
                    user.password_hash = src.password_hash
                user.last_synced_at = now
                updated += 1
        await session.flush()

    # Deactivate users that disappeared from MySQL
    result = await session.execute(
        select(User).where(User.external_id.isnot(None), User.is_active.is_(True))
    )
    deactivated = 0
    for user in result.scalars():
        if user.external_id not in seen_external_ids:
            user.is_active = False
            deactivated += 1
            log.info("Deactivated user %s (external_id=%s) — not in MySQL pull", user.email, user.external_id)
    await session.flush()
    return added, updated, deactivated


async def run_sync(session: AsyncSession, source) -> SyncReport:
    """Pull MySQL → upsert into Postgres. Returns SyncReport."""
    import time
    start = time.monotonic()
    report = SyncReport()

    try:
        ra, ru = await _sync_roles(session, source)
        report.roles_added, report.roles_updated = ra, ru
    except Exception as e:
        report.errors.append(f"roles: {e}")
        log.exception("Role sync failed")

    try:
        da, du = await _sync_departments(session, source)
        report.departments_added, report.departments_updated = da, du
    except Exception as e:
        report.errors.append(f"departments: {e}")
        log.exception("Department sync failed")

    try:
        ua, uu, ud = await _sync_users(session, source)
        report.users_added, report.users_updated, report.users_deactivated = ua, uu, ud
    except Exception as e:
        report.errors.append(f"users: {e}")
        log.exception("User sync failed")

    await session.commit()
    report.duration_ms = (time.monotonic() - start) * 1000
    return report
