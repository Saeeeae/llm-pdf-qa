"""Read-only async MySQL connection to the in-house HR DB (asyncmy).

Source schema:
- USER_INFO: USER_ID, USER_NAME, LOGIN_PWD, LOGIN_DENY_YN,
             DEPT_ID, DEPT_NAME, CMP_EMAIL, POS_ID, POS_NAME, EMP_STATUS

Roles (직급) and departments (부서) are denormalized inside USER_INFO,
so we derive them via SELECT DISTINCT. SQL `AS` aliases translate
in-house column names to the internal dict contract consumed by
source_rows.py / syncer.py — keeping those layers untouched.
"""
import os
import re
from typing import AsyncIterator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str, kind: str) -> str:
    """Validate SQL identifier (table/column) before f-string interpolation.

    Source value comes from operator-controlled env, but an accidental backtick
    or shell-injection-style value would corrupt the query. Hard-fail at
    startup rather than producing broken SQL at runtime.
    """
    if not _IDENT_RE.match(name or ""):
        raise RuntimeError(
            f"invalid {kind} identifier {name!r} — must match [A-Za-z_][A-Za-z0-9_]*"
        )
    return name


# In-house source-of-truth is USER_INFO (denormalized — POS/DEPT inline).
# No separate role/department tables; we derive via SELECT DISTINCT below.
_MYSQL_URL = os.getenv("MYSQL_URL", "mysql+asyncmy://user:pass@hr-host:3306/hr")
_TABLE_USERS = _safe_ident(os.getenv("MYSQL_TABLE_USERS", "USER_INFO"), "table")
_BATCH_SIZE = int(os.getenv("MYSQL_SYNC_BATCH_SIZE", "1000"))
_POOL_SIZE = int(os.getenv("MYSQL_POOL_SIZE", "5"))
_POOL_RECYCLE = int(os.getenv("MYSQL_POOL_RECYCLE_SECONDS", "1800"))


def make_mysql_engine() -> AsyncEngine:
    return create_async_engine(
        _MYSQL_URL,
        pool_size=_POOL_SIZE,
        pool_recycle=_POOL_RECYCLE,  # MySQL default idle timeout is 8h
        pool_pre_ping=True,
        echo=False,
    )


class MySQLSource:
    """Wraps MySQL engine with typed fetch methods over the in-house HR DB."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def fetch_roles(self) -> list[dict]:
        # Source has no roles table — derive from POS_ID/POS_NAME.
        # permissions/description are not exposed by the source schema.
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(
                    f"SELECT DISTINCT POS_ID AS id, POS_NAME AS name, "
                    f"NULL AS permissions, NULL AS description "
                    f"FROM `{_TABLE_USERS}` "
                    f"WHERE EMP_STATUS = 'W' AND POS_ID <> '0'"
                )
            )
            return [dict(row._mapping) for row in result.fetchall()]

    async def fetch_departments(self) -> list[dict]:
        # Source has no departments table — derive from DEPT_ID/DEPT_NAME.
        # parent_id is NULL: the source schema does not expose org hierarchy.
        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(
                    f"SELECT DISTINCT DEPT_ID AS id, DEPT_NAME AS name, "
                    f"NULL AS parent_id "
                    f"FROM `{_TABLE_USERS}` "
                    f"WHERE EMP_STATUS = 'W' AND DEPT_ID IS NOT NULL"
                )
            )
            return [dict(row._mapping) for row in result.fetchall()]

    async def fetch_users(self) -> AsyncIterator[list[dict]]:
        """Yields batches of active users via offset pagination.

        Filters: EMP_STATUS='W' (재직 중), POS_ID<>'0' (정식 직급).
        LOGIN_DENY_YN='Y' folds to is_active=0 so locked accounts sync as inactive.
        """
        offset = 0
        async with self.engine.connect() as conn:
            while True:
                result = await conn.execute(
                    text(
                        f"SELECT USER_ID AS id, "
                        f"CMP_EMAIL AS email, "
                        f"USER_NAME AS name, "
                        f"DEPT_ID AS department_id, "
                        f"POS_ID AS role_id, "
                        f"CASE WHEN LOGIN_DENY_YN = 'Y' THEN 0 ELSE 1 END AS is_active, "
                        f"LOGIN_PWD AS password_hash, "
                        f"NULL AS updated_at "
                        f"FROM `{_TABLE_USERS}` "
                        f"WHERE EMP_STATUS = 'W' AND POS_ID <> '0' "
                        f"ORDER BY USER_ID LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": _BATCH_SIZE, "offset": offset},
                )
                rows = [dict(row._mapping) for row in result.fetchall()]
                if not rows:
                    break
                yield rows
                offset += _BATCH_SIZE
