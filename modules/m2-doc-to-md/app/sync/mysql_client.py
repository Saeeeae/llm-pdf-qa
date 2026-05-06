"""Read-only async MySQL clients for m2's two upstream DBs.

- File metadata (F0_00001_F) lives on the search server.
- Folder ACL (PDiskFolderPermission2) lives on the HR DB (same server m1
  uses for USER_INFO, hence m1 → m2 ordering: m2 reads ACL after m1 has
  refreshed identity).

Both URLs are independent so deployments can point them anywhere.
"""
import os
import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str, kind: str) -> str:
    if not _IDENT_RE.match(name or ""):
        raise RuntimeError(
            f"invalid {kind} identifier {name!r} — must match [A-Za-z_][A-Za-z0-9_]*"
        )
    return name


_FILE_URL = os.getenv(
    "M2_MYSQL_FILE_URL",
    "mysql+asyncmy://user:pass@search-host:3306/search",
)
_HR_URL = os.getenv(
    "M2_MYSQL_HR_URL",
    "mysql+asyncmy://user:pass@hr-host:3306/hr",
)

_TABLE_FILES = _safe_ident(
    os.getenv("M2_MYSQL_TABLE_FILES", "F0_00001_F"), "table"
)
_TABLE_FOLDER_PERMS = _safe_ident(
    os.getenv("M2_MYSQL_TABLE_FOLDER_PERMS", "PDiskFolderPermission2"), "table"
)
_POOL_SIZE = int(os.getenv("MYSQL_POOL_SIZE", "5"))
_POOL_RECYCLE = int(os.getenv("MYSQL_POOL_RECYCLE_SECONDS", "1800"))


def make_file_engine() -> AsyncEngine:
    return create_async_engine(
        _FILE_URL, pool_size=_POOL_SIZE, pool_recycle=_POOL_RECYCLE,
        pool_pre_ping=True, echo=False,
    )


def make_hr_engine() -> AsyncEngine:
    # HR pool is smaller — m2 only reads ACLs, not bulk user rows.
    return create_async_engine(
        _HR_URL, pool_size=max(1, _POOL_SIZE - 2), pool_recycle=_POOL_RECYCLE,
        pool_pre_ping=True, echo=False,
    )


async def fetch_files(engine: AsyncEngine) -> list[dict]:
    """Pull file metadata + per-file ACL columns from F0_00001_F."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                f"SELECT FileName, FilePath, UserFilePath, ModifiedDate, "
                f"AllowOrgList, AllowPersonalList, FileSize, FileExt "
                f"FROM `{_TABLE_FILES}`"
            )
        )
        return [dict(row._mapping) for row in result.fetchall()]


async def fetch_folder_permissions(engine: AsyncEngine) -> dict[str, list[str]]:
    """Folder → list of USER_IDs from PDiskFolderPermission2.

    Source row is (Folder, USER); we group server-side and return a mapping
    so callers can look up by folder path directly.
    """
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                f"SELECT Folder, GROUP_CONCAT(USER SEPARATOR ',') AS USERS "
                f"FROM `{_TABLE_FOLDER_PERMS}` GROUP BY Folder"
            )
        )
        out: dict[str, list[str]] = {}
        for row in result.fetchall():
            d = dict(row._mapping)
            users = d.get("USERS") or ""
            out[d["Folder"]] = [u for u in users.split(",") if u]
        return out
