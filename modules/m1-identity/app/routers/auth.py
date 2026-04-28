import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as aioredis
from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_event
from ..auth.jwt import create_access_token, get_current_user
from ..auth.password import verify_password
from ..db import get_db
from ..models import RefreshToken, User

router = APIRouter(prefix="/auth")

_ph = PasswordHasher()
REFRESH_TOKEN_DAYS = 7
LOCKOUT_FAILS = 5
LOCKOUT_TTL = 900  # 15 minutes


def _redis() -> Optional[aioredis.Redis]:
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        return aioredis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    r = _redis()
    fail_key = f"login:fail:{body.email}"

    if r:
        try:
            fails = await r.get(fail_key)
            if fails and int(fails) >= LOCKOUT_FAILS:
                ttl = await r.ttl(fail_key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Account temporarily locked",
                    headers={"Retry-After": str(ttl)},
                )
        except HTTPException:
            raise
        except Exception:
            pass

    result = await db.execute(select(User).where(User.email == body.email, User.is_active.is_(True)))
    user = result.scalar_one_or_none()

    def _fail():
        if r:
            import asyncio
            asyncio.ensure_future(_increment_fail(r, fail_key))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user:
        _fail()

    ok, new_hash = verify_password(body.password, user.password_hash)
    if not ok:
        _fail()

    # Clear fail counter on success
    if r:
        try:
            await r.delete(fail_key)
        except Exception:
            pass

    # Update last_login_at (and persist hash upgrade if needed)
    update_vals: dict = {"last_login_at": datetime.now(timezone.utc)}
    if new_hash:
        update_vals["password_hash"] = new_hash
    await db.execute(update(User).where(User.id == user.id).values(**update_vals))

    perms: list[str] = user.role.permissions if user.role and user.role.permissions else []
    access_token = create_access_token(str(user.id), user.role.name if user.role else "", perms)

    raw_refresh = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_refresh)
    rt = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        device_info=request.headers.get("User-Agent", "")[:512],
    )
    db.add(rt)
    await db.commit()

    ip = request.client.host if request.client else None
    await log_event(db, user.id, "login", "auth", None, ip)

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


async def _increment_fail(r, key: str):
    try:
        await r.incr(key)
        await r.expire(key, LOCKOUT_TTL)
    except Exception:
        pass


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    token_hash = _hash_token(body.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    rt = result.scalar_one_or_none()

    ip = request.client.host if request.client else None

    if not rt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if rt.revoked:
        # Token theft detected: revoke all user refresh tokens
        await db.execute(
            update(RefreshToken).where(RefreshToken.user_id == rt.user_id).values(revoked=True)
        )
        await db.commit()
        await log_event(db, rt.user_id, "token_theft_detected", "auth", None, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token reuse detected")

    if rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    # Revoke old token — commit immediately to prevent race/reuse
    rt.revoked = True
    await db.commit()

    user_result = await db.execute(select(User).where(User.id == rt.user_id, User.is_active.is_(True)))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    perms: list[str] = user.role.permissions if user.role and user.role.permissions else []
    access_token = create_access_token(str(user.id), user.role.name if user.role else "", perms)

    raw_refresh = secrets.token_urlsafe(48)
    new_hash = _hash_token(raw_refresh)
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        device_info=rt.device_info,
    )
    db.add(new_rt)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_db)):
    token_hash = _hash_token(body.refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    rt = result.scalar_one_or_none()
    if rt and not rt.revoked:
        rt.revoked = True
        await db.commit()


@router.get("/me")
async def me(payload: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.name if user.role else None,
        "permissions": user.role.permissions if user.role else [],
    }
