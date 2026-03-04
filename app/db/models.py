from datetime import datetime, timezone
from pgvector.sqlalchemy import Vector
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
    images = relationship("DocImage", back_populates="document", cascade="all, delete-orphan")


class DocImage(Base):
    __tablename__ = "doc_image"

    image_id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("document.doc_id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer)
    image_path = Column(Text, nullable=False)
    image_type = Column(String(20))
    width = Column(Integer)
    height = Column(Integer)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="images")


class DocChunk(Base):
    __tablename__ = "doc_chunk"

    chunk_id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("document.doc_id", ondelete="CASCADE"), nullable=False)
    chunk_idx = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_cnt = Column(Integer, default=0)
    page_number = Column(Integer)
    embedding = Column(Vector(1024))
    embed_model = Column(String(100))
    chunk_type = Column(String(20), default="text")
    image_id = Column(Integer, ForeignKey("doc_image.image_id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="chunks")
    image = relationship("DocImage")


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


class Workspace(Base):
    __tablename__ = "workspace"

    ws_id = Column(Integer, primary_key=True, autoincrement=True)
    ws_name = Column(String(200), nullable=False)
    owner_dept_id = Column(Integer, ForeignKey("department.dept_id", ondelete="RESTRICT"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)


class RefreshToken(Base):
    __tablename__ = "refresh_token"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(Text, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ip_address = Column(String(45))

    user = relationship("User", viewonly=True)


class UserPreference(Base):
    __tablename__ = "user_preference"

    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    preferences = Column(JSON, default=lambda: {"search_scope": "all", "web_search": False, "theme": "light"})

    user = relationship("User", viewonly=True)


class LLMConfig(Base):
    __tablename__ = "llm_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False)
    vllm_url = Column(String(255), nullable=False, default="http://vllm-server:8001/v1")
    system_prompt = Column(Text, default="당신은 사내 문서를 기반으로 답변하는 AI 어시스턴트입니다. 제공된 문서 내용을 바탕으로 정확하고 도움이 되는 답변을 제공하세요.")
    max_tokens = Column(Integer, default=4096)
    temperature = Column(Float, default=0.7)
    top_p = Column(Float, default=0.9)
    context_chunks = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ChatSession(Base):
    __tablename__ = "chat_session"

    session_id = Column(Integer, primary_key=True, autoincrement=True)
    ws_id = Column(Integer, ForeignKey("workspace.ws_id", ondelete="SET NULL"))
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    title = Column(String(300))
    session_type = Column(String(20), nullable=False, default="private")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])


class ChatMessage(Base):
    __tablename__ = "chat_msg"

    msg_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_session.session_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"))
    sender_type = Column(String(10), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session = relationship("ChatSession", back_populates="messages")
    references = relationship("MsgRef", back_populates="message", cascade="all, delete-orphan")


class MsgRef(Base):
    __tablename__ = "msg_ref"

    ref_id = Column(Integer, primary_key=True, autoincrement=True)
    msg_id = Column(Integer, ForeignKey("chat_msg.msg_id", ondelete="CASCADE"), nullable=False)
    doc_id = Column(Integer, ForeignKey("document.doc_id", ondelete="SET NULL"))
    chunk_id = Column(Integer, ForeignKey("doc_chunk.chunk_id", ondelete="SET NULL"))
    web_url = Column(String(2048))
    relevance_score = Column(Float)

    message = relationship("ChatMessage", back_populates="references")
    document = relationship("Document", viewonly=True)
    chunk = relationship("DocChunk", viewonly=True)


class WebSearchLog(Base):
    __tablename__ = "web_search_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"))
    session_id = Column(Integer, ForeignKey("chat_session.session_id", ondelete="SET NULL"))
    query = Column(Text, nullable=False)
    was_blocked = Column(Boolean, default=False)
    block_reason = Column(Text)
    results_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FolderAccess(Base):
    __tablename__ = "folder_access"

    access_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(Integer, ForeignKey("doc_folder.folder_id", ondelete="CASCADE"), nullable=False)
    is_recursive = Column(Boolean, default=False)
    granted_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"))
    granted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)

    user = relationship("User", foreign_keys=[user_id], viewonly=True)
    folder = relationship("DocFolder", viewonly=True)


class WsPermission(Base):
    __tablename__ = "ws_permission"

    permission_id = Column(Integer, primary_key=True, autoincrement=True)
    ws_id = Column(Integer, ForeignKey("workspace.ws_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")

    workspace = relationship("Workspace", viewonly=True)
    user = relationship("User", viewonly=True)


class WsInvitation(Base):
    __tablename__ = "ws_invitation"

    invite_id = Column(Integer, primary_key=True, autoincrement=True)
    ws_id = Column(Integer, ForeignKey("workspace.ws_id", ondelete="CASCADE"), nullable=False)
    inviter_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    invitee_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    responded_at = Column(DateTime(timezone=True))

    workspace = relationship("Workspace", viewonly=True)
    inviter = relationship("User", foreign_keys=[inviter_id], viewonly=True)
    invitee = relationship("User", foreign_keys=[invitee_id], viewonly=True)


class SessionParticipant(Base):
    __tablename__ = "session_participant"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_session.session_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session = relationship("ChatSession", viewonly=True)
    user = relationship("User", viewonly=True)


class AccessRequest(Base):
    __tablename__ = "access_request"

    req_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    target_ws_id = Column(Integer, ForeignKey("workspace.ws_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    approve_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True))

    user = relationship("User", foreign_keys=[user_id], viewonly=True)
    workspace = relationship("Workspace", viewonly=True)
