"""
db.py — async SQLAlchemy engine for M7 admin backend.

Source URL resolution order:
  1. POSTGRES_RO_URL     — preferred read-only replica (asyncpg)
  2. POSTGRES_ASYNC_URL  — async-explicit URL (asyncpg)
  3. POSTGRES_URL        — common project URL; auto-converted from psycopg → asyncpg

Engine is created lazily on first use so import works even when env vars
are absent (tests, CI).
"""
import os
from typing import Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy import text

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


def _make_async_url() -> str:
    raw = (
        os.getenv("POSTGRES_RO_URL")
        or os.getenv("POSTGRES_ASYNC_URL")
        or os.getenv("POSTGRES_URL", "")
    )
    if not raw:
        # Fallback so SQLAlchemy doesn't error at import time
        return "postgresql+asyncpg://postgres:postgres@localhost:5432/ragdb"
    for old, new in [
        ("postgresql+psycopg://", "postgresql+asyncpg://"),
        ("postgresql://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
    ]:
        if raw.startswith(old):
            return raw.replace(old, new, 1)
    return raw


def _get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(
            _make_async_url(),
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
        _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    _get_engine()
    async with _session_factory() as session:  # type: ignore[misc]
        yield session


async def check_db_connectivity() -> bool:
    try:
        eng = _get_engine()
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
