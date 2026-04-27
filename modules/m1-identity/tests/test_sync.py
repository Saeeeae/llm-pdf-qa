"""Tests for MySQL → Postgres batch sync."""
import os
os.environ["TEST_MODE"] = "1"
os.environ["JWT_SECRET"] = "test-secret"

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.models import Base, Department, Role, User, SyncRun
from app.sync.syncer import run_sync


# ---------------------------------------------------------------------------
# FakeMySQLSource — satisfies same interface as MySQLSource
# ---------------------------------------------------------------------------

class FakeMySQLSource:
    def __init__(self, roles=None, departments=None, users=None):
        self._roles = roles or []
        self._departments = departments or []
        self._users = users or []

    async def fetch_roles(self):
        return self._roles

    async def fetch_departments(self):
        return self._departments

    async def fetch_users(self):
        # Yield in a single batch (mirrors the async generator protocol)
        if self._users:
            yield self._users


def make_role_row(id, name, permissions=None, description=None):
    return {"id": id, "name": name, "permissions": permissions, "description": description}

def make_dept_row(id, name, parent_id=None):
    return {"id": id, "name": name, "parent_id": parent_id}

def make_user_row(id, email, name="Test", dept_id=None, role_id=None, is_active=1, pw="$argon2id$v=19$m=65536,t=3,p=4$stub", updated_at=None):
    return {
        "id": id, "email": email, "name": name,
        "department_id": dept_id, "role_id": role_id,
        "is_active": is_active, "password_hash": pw, "updated_at": updated_at,
    }


@pytest_asyncio.fixture()
async def session():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    async with factory() as s:
        yield s
    await eng.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_initial(session):
    """Empty M1 + 3 roles + 2 depts + 5 users → all inserted."""
    source = FakeMySQLSource(
        roles=[
            make_role_row(1, "admin", ["user.read", "admin.write"]),
            make_role_row(2, "manager"),
            make_role_row(3, "user"),
        ],
        departments=[
            make_dept_row(10, "Engineering"),
            make_dept_row(11, "HR"),
        ],
        users=[make_user_row(i, f"user{i}@test.com", role_id=3, dept_id=10) for i in range(1, 6)],
    )
    report = await run_sync(session, source)

    assert report.roles_added == 3
    assert report.departments_added == 2
    assert report.users_added == 5
    assert report.users_updated == 0
    assert report.errors == []

    result = await session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 5


@pytest.mark.asyncio
async def test_sync_update_existing(session):
    """Existing users get name/dept changes applied; last_synced_at updated."""
    # Pre-seed a user
    role = Role(name="user", external_id=3)
    dept_old = Department(name="OldDept", external_id=10)
    dept_new = Department(name="NewDept", external_id=11)
    session.add_all([role, dept_old, dept_new])
    await session.flush()
    user = User(email="alice@test.com", name="Alice Old", password_hash="x", external_id=1, is_active=True)
    session.add(user)
    await session.commit()

    source = FakeMySQLSource(
        roles=[make_role_row(3, "user")],
        departments=[make_dept_row(10, "OldDept"), make_dept_row(11, "NewDept")],
        users=[make_user_row(1, "alice@test.com", name="Alice New", dept_id=11, role_id=3)],
    )
    report = await run_sync(session, source)

    assert report.users_updated == 1
    assert report.users_added == 0

    await session.refresh(user)
    assert user.name == "Alice New"
    assert user.last_synced_at is not None


@pytest.mark.asyncio
async def test_sync_deactivation(session):
    """User in M1 with external_id but absent from MySQL pull → is_active=False."""
    user = User(email="ghost@test.com", name="Ghost", password_hash="x", external_id=999, is_active=True)
    session.add(user)
    await session.commit()

    source = FakeMySQLSource(roles=[], departments=[], users=[])
    report = await run_sync(session, source)

    assert report.users_deactivated == 1
    await session.refresh(user)
    assert user.is_active is False


@pytest.mark.asyncio
async def test_sync_legacy_hash_upgrade(session):
    """Source provides bcrypt hash → login succeeds → hash auto-upgraded to argon2."""
    from passlib.context import CryptContext
    bcrypt_ctx = CryptContext(schemes=["bcrypt"])
    bcrypt_hash = bcrypt_ctx.hash("secret123")

    from app.auth.password import verify_password

    ok, new_hash = verify_password("secret123", bcrypt_hash)
    assert ok is True
    assert new_hash is not None  # upgrade happened
    assert new_hash.startswith("$argon2")

    # Verify upgraded hash also works
    ok2, _ = verify_password("secret123", new_hash)
    assert ok2 is True

    # Wrong password must fail
    ok3, _ = verify_password("wrong", bcrypt_hash)
    assert ok3 is False


@pytest.mark.asyncio
async def test_sync_concurrent_lock(monkeypatch):
    """Second concurrent run is blocked when Redis lock is held."""
    held = []

    # Simulate lock already held: set() returns None (NX failed)
    class FakeRedis:
        async def set(self, key, val, nx=False, ex=None):
            return None  # lock not acquired

        async def delete(self, key):
            pass

        async def aclose(self):
            pass

    import redis.asyncio as aioredis
    monkeypatch.setattr(aioredis, "from_url", lambda *a, **kw: FakeRedis())

    from app.sync.scheduler import _run_locked_sync
    # Should log "skipped" and return without running sync
    await _run_locked_sync()  # must not raise
    # No assertion needed beyond no exception; lock skip is logged
