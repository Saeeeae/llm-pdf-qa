import os
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB is PostgreSQL-only; tests use SQLite which only has JSON
_TEST_MODE = os.getenv("TEST_MODE", "0") == "1"
if _TEST_MODE:
    from sqlalchemy import JSON as JSONB
    # SQLite doesn't support BigInteger autoincrement — use Integer
    PkCol: type = Integer
    FkType: type = Integer
else:
    from sqlalchemy.dialects.postgresql import JSONB  # noqa: F811
    PkCol = BigInteger
    FkType = BigInteger


class Base(DeclarativeBase):
    pass


class Department(Base):
    __tablename__ = "department"

    id: Mapped[int] = mapped_column(PkCol, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(FkType, ForeignKey("department.id"), nullable=True)
    external_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(PkCol, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    permissions: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    external_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)

    id: Mapped[int] = mapped_column(PkCol, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[Optional[int]] = mapped_column(FkType, ForeignKey("department.id"), nullable=True)
    role_id: Mapped[Optional[int]] = mapped_column(FkType, ForeignKey("roles.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    role: Mapped[Optional["Role"]] = relationship("Role", lazy="selectin")
    preferences: Mapped[Optional["UserPreference"]] = relationship(
        "UserPreference", back_populates="user", lazy="selectin", uselist=False
    )


class RefreshToken(Base):
    __tablename__ = "refresh_token"
    __table_args__ = (UniqueConstraint("token_hash"),)

    id: Mapped[int] = mapped_column(PkCol, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(FkType, ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    device_info: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class UserPreference(Base):
    __tablename__ = "user_preference"

    user_id: Mapped[int] = mapped_column(FkType, ForeignKey("users.id"), primary_key=True)
    theme: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="light")
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="en")
    settings: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="preferences")


class AccessRequest(Base):
    __tablename__ = "access_request"

    id: Mapped[int] = mapped_column(PkCol, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(FkType, ForeignKey("users.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncRun(Base):
    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(PkCol, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")  # running/success/error
    report: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_user_ts", "user_id", "ts"),)

    id: Mapped[int] = mapped_column(PkCol, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(FkType, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Column named "metadata" in DB; "meta" as Python attr to avoid SQLAlchemy reserved name
    meta: Mapped[Optional[Any]] = mapped_column("metadata", JSONB, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
