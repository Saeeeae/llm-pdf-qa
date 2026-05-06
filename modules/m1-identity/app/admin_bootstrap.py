"""Admin user bootstrap — shared by the CLI and the startup auto-bootstrap.

The user-creation endpoint at routers/users.py is RBAC-gated (admin.write),
which creates a chicken-and-egg problem on a fresh deployment: there is no
admin to create the first admin. This module bypasses RBAC by writing
directly to the DB.

Two entry points:
- ``create_admin_user`` — explicit creation (used by CLI and tests)
- ``maybe_bootstrap_admin`` — startup hook; idempotent no-op when an
  admin already exists or env vars are missing
"""
import logging
import os
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth.password import hash_password
from .models import Role, User

log = logging.getLogger(__name__)


class AdminBootstrapError(Exception):
    """Raised for unrecoverable bootstrap problems."""


async def _find_admin_role(session: AsyncSession) -> Optional[Role]:
    result = await session.execute(select(Role).where(Role.name == "admin"))
    return result.scalar_one_or_none()


async def _count_admins(session: AsyncSession) -> int:
    """Count active users with the admin role."""
    role = await _find_admin_role(session)
    if role is None:
        return 0
    result = await session.execute(
        select(func.count(User.id)).where(
            User.role_id == role.id,
            User.is_active == True,  # noqa: E712
        )
    )
    return int(result.scalar() or 0)


async def create_admin_user(
    session: AsyncSession,
    email: str,
    password: str,
    name: Optional[str] = None,
    overwrite: bool = False,
) -> User:
    """Create or replace an admin user, bypassing RBAC.

    Behavior:
    - admin role MUST exist (seeded by alembic 0001_initial). If missing,
      raises AdminBootstrapError — surfaces a real config problem rather
      than silently inventing a role.
    - If a user with the given email exists:
        - overwrite=False (default): raises AdminBootstrapError
        - overwrite=True: rotates password + reassigns admin role + activates
    - Otherwise inserts a new user with hashed password and admin role.
    """
    if not email or not password:
        raise AdminBootstrapError("email and password are required")

    role = await _find_admin_role(session)
    if role is None:
        raise AdminBootstrapError(
            "admin role not found — run migrations first (alembic upgrade head)"
        )

    result = await session.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()

    if existing is not None and not overwrite:
        raise AdminBootstrapError(
            f"user {email} already exists (use overwrite=True to rotate)"
        )

    pw_hash = hash_password(password)
    if existing is not None:
        existing.password_hash = pw_hash
        existing.role_id = role.id
        existing.is_active = True
        if name:
            existing.name = name
        user = existing
        log.info("Rotated admin %s", email)
    else:
        user = User(
            email=email,
            password_hash=pw_hash,
            name=name or email.split("@")[0],
            role_id=role.id,
            is_active=True,
        )
        session.add(user)
        log.info("Created admin %s", email)

    await session.commit()
    await session.refresh(user)
    return user


async def maybe_bootstrap_admin() -> None:
    """Startup hook: create an admin from env if none exists.

    Triggered when ``BOOTSTRAP_ADMIN_EMAIL`` and ``BOOTSTRAP_ADMIN_PASSWORD``
    are both set. Idempotent — does nothing if any active admin already
    exists, so re-deploys won't reset the password or reset the user.
    """
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    name = os.getenv("BOOTSTRAP_ADMIN_NAME")

    if not email or not password:
        log.info("Bootstrap skipped — BOOTSTRAP_ADMIN_EMAIL/PASSWORD not set")
        return

    # Late import so monkeypatched AsyncSessionLocal in tests is honored
    from . import db as db_module

    async with db_module.AsyncSessionLocal() as session:
        admin_count = await _count_admins(session)
        if admin_count > 0:
            log.info(
                "Bootstrap skipped — %d admin(s) already exist", admin_count
            )
            return
        try:
            await create_admin_user(session, email=email, password=password, name=name)
            log.info("Bootstrap created admin %s", email)
        except IntegrityError:
            # Sibling worker / replica won the race and inserted first.
            # Email is unique in DB, so the second insert hits a unique
            # violation — safe to treat as "already created".
            log.info("Bootstrap skipped — admin %s created concurrently", email)
        except AdminBootstrapError as e:
            log.error("Bootstrap failed: %s", e)
