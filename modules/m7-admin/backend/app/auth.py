"""
auth.py — JWT verification and RBAC for M7 admin backend.
Validates tokens issued by M1 identity service.
"""
import os
from typing import Optional
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError


def _require_secret(name: str) -> str:
    v = os.getenv(name)
    if not v or len(v) < 32:
        raise RuntimeError(f"{name} must be set (>=32 chars)")
    return v


_SECRET = _require_secret("JWT_SECRET")
_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

bearer = HTTPBearer(auto_error=False)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


async def current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict:
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return decode_token(creds.credentials)


def require_permission(permission: str):
    """Dependency factory: raises 403 if user lacks the required permission."""
    async def _check(user: dict = Depends(current_user)) -> dict:
        perms: list = user.get("permissions") or user.get("perm", [])
        if permission not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission}",
            )
        return user
    return _check
