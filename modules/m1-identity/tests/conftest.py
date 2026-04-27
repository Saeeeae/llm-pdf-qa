import os
os.environ["TEST_MODE"] = "1"
os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ["REDIS_URL"] = "redis://localhost:6379"

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Role, User
from app.auth.jwt import create_access_token
from argon2 import PasswordHasher

_ph = PasswordHasher()


@pytest_asyncio.fixture()
async def ctx(monkeypatch):
    """Single fixture providing (client, session, user, role) sharing one in-memory DB."""
    import app.db as db_module
    from app.main import app

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(eng, expire_on_commit=False)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(db_module, "_engine", eng)

    async with factory() as session:
        role = Role(
            name="admin",
            description="Admin",
            permissions=[
                "user.read", "user.write", "user.delete",
                "doc.read", "doc.write", "chat.use", "web.search",
                "admin.read", "admin.write", "audit.read",
            ],
        )
        session.add(role)
        await session.flush()
        user = User(
            email="admin@test.com",
            password_hash=_ph.hash("correct-password"),
            name="Admin User",
            role_id=role.id,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await session.refresh(role)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, session, user, role

    await eng.dispose()


# Convenience aliases
@pytest_asyncio.fixture()
async def client(ctx):
    c, *_ = ctx
    yield c


@pytest_asyncio.fixture()
async def db_with_user(ctx):
    c, session, user, role = ctx
    yield session, user, role


def make_token(user_id: int, role: str = "admin", perms: list = None) -> str:
    if perms is None:
        perms = [
            "user.read", "user.write", "user.delete",
            "doc.read", "doc.write", "chat.use", "web.search",
            "admin.read", "admin.write", "audit.read",
        ]
    return create_access_token(str(user_id), role, perms)
