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


# Default role permission sets (seeded via migration)
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [p.value for p in Permission],
    "manager": [
        Permission.user_read.value,
        Permission.doc_read.value,
        Permission.doc_write.value,
        Permission.chat_use.value,
        Permission.admin_read.value,
        Permission.audit_read.value,
    ],
    "user": [
        Permission.doc_read.value,
        Permission.chat_use.value,
    ],
}


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
