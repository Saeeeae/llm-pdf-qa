import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from .models import Base

# TEST_MODE=1 uses aiosqlite in-memory; production uses asyncpg
_TEST_MODE = os.getenv("TEST_MODE", "0") == "1"

if _TEST_MODE:
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    _engine = create_async_engine(DATABASE_URL, echo=False)
else:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ragdb"
    )
    _engine = create_async_engine(
        DATABASE_URL,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )

AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables (used in test mode and first-run dev)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
