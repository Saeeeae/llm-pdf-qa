from enum import Enum
from fastapi import Depends, HTTPException, status
from .jwt import get_current_user


class Permission(str, Enum):
    user_read = "user.read"
    user_write = "user.write"
    user_delete = "user.delete"
    doc_read = "doc.read"
    doc_write = "doc.write"
    chat_use = "chat.use"
    web_search = "web.search"
    admin_read = "admin.read"
    admin_write = "admin.write"
    audit_read = "audit.read"


# Role → permissions mapping is the SQL seed in alembic/versions/0001_initial.py.
# At login, app/routers/auth.py reads `user.role.permissions` directly from the
# DB, so there is no Python-side ROLE_PERMISSIONS map to keep in sync.


def require(*perms: Permission):
    """FastAPI dependency that enforces all listed permissions."""
    async def _check(payload: dict = Depends(get_current_user)):
        user_perms: list[str] = payload.get("perm", [])
        missing = [p.value for p in perms if p.value not in user_perms]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {missing}",
            )
        return payload
    return _check
