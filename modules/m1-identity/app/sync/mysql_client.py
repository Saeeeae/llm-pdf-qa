"""Read-only async MySQL connection using asyncmy."""
import os
import re
from typing import AsyncIterator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str, env_var: str) -> str:
    """Validate table identifiers to prevent SQL injection through env vars."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"Invalid SQL identifier in {env_var}: {name!r}")
    return name


_MYSQL_URL = os.getenv("MYSQL_URL", "mysql+asyncmy://user:pass@mysql-host:3306/hr")
_TABLE_USERS = _safe_ident(os.getenv("MYSQL_TABLE_USERS", "hr_users"), "MYSQL_TABLE_USERS")
_TABLE_ROLES = _safe_ident(os.getenv("MYSQL_TABLE_ROLES", "hr_roles"), "MYSQL_TABLE_ROLES")
_TABLE_DEPARTMENTS = _safe_ident(
    os.getenv("MYSQL_TABLE_DEPARTMENTS", "hr_departments"), "MYSQL_TABLE_DEPARTMENTS"
)
_BATCH_SIZE = int(os.getenv("MYSQL_SYNC_BATCH_SIZE", "1000"))


def make_mysql_engine() -> AsyncEngine:
    return create_async_engine(
        _MYSQL_URL,
        pool_size=5,
        pool_recycle=1800,  # MySQL default idle timeout is 8h; 30min keeps connection fresh
        pool_pre_ping=True,
        echo=False,
    )


class MySQLSource:
    """Wraps MySQL engine with typed fetch methods."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def fetch_roles(self) -> list[dict]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(f"SELECT id, name, permissions, description FROM {_TABLE_ROLES}")
            )
            return [dict(row._mapping) for row in result.fetchall()]

    async def fetch_departments(self) -> list[dict]:
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(f"SELECT id, name, parent_id FROM {_TABLE_DEPARTMENTS}")
            )
            return [dict(row._mapping) for row in result.fetchall()]

    async def fetch_users(self) -> AsyncIterator[list[dict]]:
        """Yields batches of users using offset pagination."""
        offset = 0
        async with self.engine.connect() as conn:
            while True:
                result = await conn.execute(
                    text(
                        f"SELECT id, email, name, department_id, role_id, is_active, "
                        f"password_hash, updated_at FROM {_TABLE_USERS} "
                        f"ORDER BY id LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": _BATCH_SIZE, "offset": offset},
                )
                rows = [dict(row._mapping) for row in result.fetchall()]
                if not rows:
                    break
                yield rows
                offset += _BATCH_SIZE
