from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, BigInteger, Boolean, Float,
    ForeignKey, DateTime, JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Department(Base):
    __tablename__ = "department"

    dept_id = Column(Integer, primary_key=True, autoincrement=True)
    parent_dept_id = Column(Integer, ForeignKey("department.dept_id", ondelete="SET NULL"))
    name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Role(Base):
    __tablename__ = "roles"

    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(50), nullable=False, unique=True)
    auth_level = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    pwd = Column(Text, nullable=False)
    usr_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    dept_id = Column(Integer, ForeignKey("department.dept_id", ondelete="RESTRICT"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.role_id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True))
    pwd_day = Column(Integer, default=90)
    failure = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)


class DocFolder(Base):
    __tablename__ = "doc_folder"

    folder_id = Column(Integer, primary_key=True, autoincrement=True)
    parent_folder_id = Column(Integer, ForeignKey("doc_folder.folder_id", ondelete="CASCADE"))
    folder_name = Column(String(255), nullable=False)
    folder_path = Column(Text, nullable=False)
    dept_id = Column(Integer, ForeignKey("department.dept_id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Document(Base):
    __tablename__ = "document"

    doc_id = Column(Integer, primary_key=True, autoincrement=True)
    folder_id = Column(Integer, ForeignKey("doc_folder.folder_id", ondelete="SET NULL"))
    file_name = Column(String(500), nullable=False)
    path = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)
    hash = Column(String(64), unique=True, nullable=False)
    size = Column(BigInteger)
    dept_id = Column(Integer, ForeignKey("department.dept_id", ondelete="RESTRICT"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.role_id", ondelete="RESTRICT"), nullable=False)
    total_page_cnt = Column(Integer, default=0)
    language = Column(String(10), default="ko")
    version = Column(Integer, default=1)
    status = Column(String(20), nullable=False, default="pending")
    error_msg = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    chunks = relationship("DocChunk", back_populates="document", cascade="all, delete-orphan")


class DocChunk(Base):
    __tablename__ = "doc_chunk"

    chunk_id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("document.doc_id", ondelete="CASCADE"), nullable=False)
    chunk_idx = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_cnt = Column(Integer, default=0)
    page_number = Column(Integer)
    qdrant_id = Column(String(64))
    embed_model = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="chunks")


class SystemJob(Base):
    __tablename__ = "system_job"

    job_id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(200), nullable=False)
    job_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="idle")
    config_json = Column(JSON)
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    last_error = Column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"))
    action_type = Column(String(50), nullable=False)
    target_type = Column(String(50))
    target_id = Column(Integer)
    description = Column(Text)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SystemHealth(Base):
    __tablename__ = "system_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_name = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    response_time_ms = Column(Float)
    metadata_json = Column(JSON)
    checked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
