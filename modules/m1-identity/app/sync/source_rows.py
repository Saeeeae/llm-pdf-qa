"""Pydantic models for MySQL source rows."""
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class SourceRole(BaseModel):
    external_id: int
    name: str
    permissions: Optional[Any] = None
    description: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "SourceRole":
        return cls(
            external_id=row["id"],
            name=row["name"],
            permissions=row.get("permissions"),
            description=row.get("description"),
        )


class SourceDepartment(BaseModel):
    external_id: int
    name: str
    parent_external_id: Optional[int] = None

    @classmethod
    def from_row(cls, row: dict) -> "SourceDepartment":
        return cls(
            external_id=row["id"],
            name=row["name"],
            parent_external_id=row.get("parent_id"),
        )


class SourceUser(BaseModel):
    external_id: int
    email: str
    name: Optional[str] = None
    department_external_id: Optional[int] = None
    role_external_id: Optional[int] = None
    is_active: bool = True
    password_hash: Optional[str] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "SourceUser":
        return cls(
            external_id=row["id"],
            email=row["email"],
            name=row.get("name"),
            department_external_id=row.get("department_id"),
            role_external_id=row.get("role_id"),
            is_active=bool(row.get("is_active", 1)),
            password_hash=row.get("password_hash"),
            updated_at=row.get("updated_at"),
        )
