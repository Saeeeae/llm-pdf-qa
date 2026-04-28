from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.jwt import get_current_user
from ..auth.rbac import Permission, require
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/users")


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    is_active: bool
    role_id: Optional[int]
    department_id: Optional[int]


class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role_id: Optional[int] = None
    department_id: Optional[int] = None


class UserPatch(BaseModel):
    name: Optional[str] = None
    department_id: Optional[int] = None
    role_id: Optional[int] = None


@router.get("", response_model=list[UserOut])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: dict = Depends(require(Permission.admin_read)),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    result = await db.execute(select(User).offset(offset).limit(size))
    return [
        UserOut(id=u.id, email=u.email, name=u.name, is_active=u.is_active,
                role_id=u.role_id, department_id=u.department_id)
        for u in result.scalars().all()
    ]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _: dict = Depends(require(Permission.admin_write)),
    db: AsyncSession = Depends(get_db),
):
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    pw_hash = ph.hash(body.password)
    user = User(
        email=body.email,
        password_hash=pw_hash,
        name=body.name,
        role_id=body.role_id,
        department_id=body.department_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut(id=user.id, email=user.email, name=user.name, is_active=user.is_active,
                   role_id=user.role_id, department_id=user.department_id)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_self = str(user_id) == payload.get("sub")
    has_perm = Permission.user_read.value in payload.get("perm", [])
    if not is_self and not has_perm:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut(id=user.id, email=user.email, name=user.name, is_active=user.is_active,
                   role_id=user.role_id, department_id=user.department_id)


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: int,
    body: UserPatch,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_self = str(user_id) == payload.get("sub")
    has_perm = Permission.user_write.value in payload.get("perm", [])
    if not is_self and not has_perm:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.name is not None:
        user.name = body.name
    if body.department_id is not None:
        user.department_id = body.department_id
    # Only admin (user.write perm) can change role
    if body.role_id is not None and has_perm:
        user.role_id = body.role_id

    await db.commit()
    await db.refresh(user)
    return UserOut(id=user.id, email=user.email, name=user.name, is_active=user.is_active,
                   role_id=user.role_id, department_id=user.department_id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    _: dict = Depends(require(Permission.user_delete)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False
    await db.commit()
