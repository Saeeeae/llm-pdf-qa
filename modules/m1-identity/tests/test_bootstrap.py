"""admin_bootstrap unit tests.

Covers:
- create_admin_user happy path (new + duplicate + overwrite)
- create_admin_user fails when admin role missing (config sanity)
- maybe_bootstrap_admin idempotency (skip when admin exists)
- maybe_bootstrap_admin no-op when env unset
"""
import os
os.environ["TEST_MODE"] = "1"
os.environ.setdefault("JWT_SECRET", "x" * 32)

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Role, User


@pytest_asyncio.fixture()
async def session_factory(monkeypatch):
    """In-memory SQLite session, with admin role pre-seeded."""
    import app.db as db_module

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(db_module, "_engine", eng)

    async with factory() as s:
        s.add(Role(
            name="admin",
            description="Admin",
            permissions=["admin.read", "admin.write"],
        ))
        await s.commit()

    yield factory
    await eng.dispose()


@pytest_asyncio.fixture()
async def session_factory_no_role(monkeypatch):
    """In-memory SQLite session WITHOUT admin role — exercises error path."""
    import app.db as db_module

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(db_module, "_engine", eng)

    yield factory
    await eng.dispose()


@pytest.mark.asyncio
async def test_create_admin_new_user(session_factory):
    from app.admin_bootstrap import create_admin_user

    async with session_factory() as s:
        user = await create_admin_user(
            s, email="root@example.com", password="strong-secret-123", name="Root"
        )
    assert user.email == "root@example.com"
    assert user.name == "Root"
    assert user.is_active is True
    assert user.password_hash.startswith("$argon2")


@pytest.mark.asyncio
async def test_create_admin_default_name_from_email(session_factory):
    from app.admin_bootstrap import create_admin_user

    async with session_factory() as s:
        user = await create_admin_user(
            s, email="ops@example.com", password="strong-secret-123"
        )
    assert user.name == "ops"  # local-part of email


@pytest.mark.asyncio
async def test_create_admin_duplicate_without_overwrite(session_factory):
    from app.admin_bootstrap import AdminBootstrapError, create_admin_user

    async with session_factory() as s:
        await create_admin_user(s, email="dup@example.com", password="pw1-strong")
    async with session_factory() as s:
        with pytest.raises(AdminBootstrapError, match="already exists"):
            await create_admin_user(s, email="dup@example.com", password="pw2-strong")


@pytest.mark.asyncio
async def test_create_admin_overwrite_rotates_password(session_factory):
    from app.admin_bootstrap import create_admin_user

    async with session_factory() as s:
        first = await create_admin_user(s, email="rot@example.com", password="old-secret-123")
    old_hash = first.password_hash

    async with session_factory() as s:
        second = await create_admin_user(
            s, email="rot@example.com", password="new-secret-456", overwrite=True
        )
    assert second.id == first.id  # same row
    assert second.password_hash != old_hash
    assert second.is_active is True


@pytest.mark.asyncio
async def test_create_admin_missing_role_raises(session_factory_no_role):
    from app.admin_bootstrap import AdminBootstrapError, create_admin_user

    async with session_factory_no_role() as s:
        with pytest.raises(AdminBootstrapError, match="admin role not found"):
            await create_admin_user(s, email="x@y.com", password="pw-strong")


@pytest.mark.asyncio
async def test_maybe_bootstrap_creates_when_no_admin(session_factory, monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "auto@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "auto-secret-123")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_NAME", "Auto Admin")

    from app.admin_bootstrap import maybe_bootstrap_admin
    await maybe_bootstrap_admin()

    async with session_factory() as s:
        result = await s.execute(select(User).where(User.email == "auto@example.com"))
        user = result.scalar_one_or_none()
    assert user is not None
    assert user.name == "Auto Admin"
    assert user.is_active is True


@pytest.mark.asyncio
async def test_maybe_bootstrap_idempotent(session_factory, monkeypatch):
    """Second call is a no-op when an admin already exists."""
    from app.admin_bootstrap import create_admin_user, maybe_bootstrap_admin

    async with session_factory() as s:
        await create_admin_user(s, email="existing@example.com", password="strong-pw-1")

    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "auto@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "strong-pw-2")
    await maybe_bootstrap_admin()

    async with session_factory() as s:
        # auto@example.com must NOT have been created
        result = await s.execute(select(User).where(User.email == "auto@example.com"))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_maybe_bootstrap_noop_when_env_unset(session_factory, monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)

    from app.admin_bootstrap import maybe_bootstrap_admin
    await maybe_bootstrap_admin()  # must not raise

    async with session_factory() as s:
        result = await s.execute(select(User))
        assert result.scalars().all() == []
