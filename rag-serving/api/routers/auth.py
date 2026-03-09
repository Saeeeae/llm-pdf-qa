import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from rag_serving.api.auth.dependencies import get_current_user
from rag_serving.api.auth.jwt import create_access_token, create_refresh_token, decode_token, hash_token
from rag_serving.api.auth.password import verify_password
from shared.config import shared_settings
from shared.models.orm import Department, RefreshToken, Role, User, UserPreference
from shared.db import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    usr_name: str
    email: str
    role_name: str
    auth_level: int
    dept_name: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    user_id: int
    usr_name: str
    email: str
    role_name: str
    auth_level: int
    dept_name: str
    preferences: dict


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request):
    ip = request.client.host if request.client else None

    with get_session() as session:
        user = session.query(User).filter(User.email == req.email).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account locked")

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

        if not verify_password(req.password, user.pwd):
            user.failure = (user.failure or 0) + 1
            if user.failure >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        user.failure = 0
        user.last_login = datetime.now(timezone.utc)

        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        dept = session.query(Department).filter(Department.dept_id == user.dept_id).first()

        access_token = create_access_token(user.user_id, role.auth_level)
        refresh_token_str = create_refresh_token(user.user_id)

        rt = RefreshToken(
            user_id=user.user_id,
            token_hash=hash_token(refresh_token_str),
            expires_at=datetime.now(timezone.utc) + timedelta(days=shared_settings.jwt_refresh_expire_days),
            ip_address=ip,
        )
        session.add(rt)

        pref = session.query(UserPreference).filter(UserPreference.user_id == user.user_id).first()
        if not pref:
            session.add(UserPreference(user_id=user.user_id))

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token_str,
            user_id=user.user_id,
            usr_name=user.usr_name,
            email=user.email,
            role_name=role.role_name,
            auth_level=role.auth_level,
            dept_name=dept.name if dept else "",
        )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_token(req: RefreshRequest):
    try:
        payload = decode_token(req.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    token_hash = hash_token(req.refresh_token)
    with get_session() as session:
        rt = session.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
        ).first()
        if not rt or rt.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

        user = session.query(User).filter(User.user_id == rt.user_id, User.is_active == True).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        access_token = create_access_token(user.user_id, role.auth_level)

    return AccessTokenResponse(access_token=access_token)


@router.post("/logout", status_code=204)
def logout(req: RefreshRequest):
    token_hash = hash_token(req.refresh_token)
    with get_session() as session:
        rt = session.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
        if rt:
            rt.revoked = True


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    with get_session() as session:
        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        dept = session.query(Department).filter(Department.dept_id == user.dept_id).first()
        pref = session.query(UserPreference).filter(UserPreference.user_id == user.user_id).first()

    return MeResponse(
        user_id=user.user_id,
        usr_name=user.usr_name,
        email=user.email,
        role_name=role.role_name if role else "",
        auth_level=role.auth_level if role else 0,
        dept_name=dept.name if dept else "",
        preferences=pref.preferences if pref else {},
    )
