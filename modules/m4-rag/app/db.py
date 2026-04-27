import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# TEST_MODE=1 → aiosqlite in-memory (no pgvector; retriever tests use mocks)
_TEST_MODE = os.getenv("TEST_MODE", "0") == "1"

if _TEST_MODE:
    _DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    _engine = create_async_engine(_DATABASE_URL, echo=False)
else:
    _DATABASE_URL = os.getenv(
        "POSTGRES_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ragdb",
    )
    _engine = create_async_engine(
        _DATABASE_URL,
        pool_size=15,
        max_overflow=5,
        pool_pre_ping=True,
        echo=False,
    )

AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
