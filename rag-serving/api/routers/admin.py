import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, text

from rag_serving.api.auth.dependencies import get_current_user, require_admin
from rag_serving.api.auth.password import hash_password
from shared.models.orm import (
    AuditLog, Department, Document, LLMConfig, PipelineLog,
    QueryLog, Role, User,
)
from shared.db import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


# --- User Management ---

class UserListItem(BaseModel):
    user_id: int
    usr_name: str
    email: str
    role_name: str
    dept_name: str
    is_active: bool
    last_login: str | None
    created_at: str


class CreateUserRequest(BaseModel):
    usr_name: str
    email: str
    password: str
    dept_id: int
    role_id: int


class UpdateUserRequest(BaseModel):
    usr_name: str | None = None
    dept_id: int | None = None
    role_id: int | None = None
    is_active: bool | None = None


@router.get("/users", response_model=list[UserListItem])
def list_users(limit: int = 50, offset: int = 0, admin: User = Depends(require_admin)):
    with get_session() as session:
        users = session.query(User).order_by(User.created_at.desc()).offset(offset).limit(limit).all()
        result = []
        for u in users:
            role = session.query(Role).filter(Role.role_id == u.role_id).first()
            dept = session.query(Department).filter(Department.dept_id == u.dept_id).first()
            result.append(UserListItem(
                user_id=u.user_id,
                usr_name=u.usr_name,
                email=u.email,
                role_name=role.role_name if role else "",
                dept_name=dept.name if dept else "",
                is_active=u.is_active,
                last_login=u.last_login.isoformat() if u.last_login else None,
                created_at=u.created_at.isoformat(),
            ))
        return result


@router.post("/users", response_model=UserListItem, status_code=201)
def create_user(req: CreateUserRequest, admin: User = Depends(require_admin)):
    with get_session() as session:
        if session.query(User).filter(User.email == req.email).first():
            raise HTTPException(status_code=409, detail="Email already exists")

        new_user = User(
            usr_name=req.usr_name,
            email=req.email,
            pwd=hash_password(req.password),
            dept_id=req.dept_id,
            role_id=req.role_id,
        )
        session.add(new_user)
        session.flush()

        role = session.query(Role).filter(Role.role_id == new_user.role_id).first()
        dept = session.query(Department).filter(Department.dept_id == new_user.dept_id).first()
        session.add(AuditLog(user_id=admin.user_id, action_type="create_user", target_type="user", target_id=new_user.user_id))

        return UserListItem(
            user_id=new_user.user_id, usr_name=new_user.usr_name, email=new_user.email,
            role_name=role.role_name if role else "", dept_name=dept.name if dept else "",
            is_active=new_user.is_active, last_login=None, created_at=new_user.created_at.isoformat(),
        )


@router.patch("/users/{user_id}", response_model=UserListItem)
def update_user(user_id: int, req: UpdateUserRequest, admin: User = Depends(require_admin)):
    with get_session() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if req.usr_name is not None:
            user.usr_name = req.usr_name
        if req.dept_id is not None:
            user.dept_id = req.dept_id
        if req.role_id is not None:
            user.role_id = req.role_id
        if req.is_active is not None:
            user.is_active = req.is_active
        user.updated_at = datetime.now(timezone.utc)

        session.add(AuditLog(user_id=admin.user_id, action_type="update_user", target_type="user", target_id=user_id))

        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        dept = session.query(Department).filter(Department.dept_id == user.dept_id).first()

        return UserListItem(
            user_id=user.user_id, usr_name=user.usr_name, email=user.email,
            role_name=role.role_name if role else "", dept_name=dept.name if dept else "",
            is_active=user.is_active, last_login=user.last_login.isoformat() if user.last_login else None,
            created_at=user.created_at.isoformat(),
        )


# --- Document Stats ---

class DocStats(BaseModel):
    total: int
    indexed: int
    failed: int
    pending: int


@router.get("/documents/stats", response_model=DocStats)
def doc_stats(admin: User = Depends(require_admin)):
    with get_session() as session:
        return DocStats(
            total=session.query(Document).count(),
            indexed=session.query(Document).filter(Document.status == "indexed").count(),
            failed=session.query(Document).filter(Document.status == "failed").count(),
            pending=session.query(Document).filter(Document.status == "pending").count(),
        )


# --- Audit Logs ---

class AuditLogItem(BaseModel):
    log_id: int
    user_id: int | None
    action_type: str
    target_type: str | None
    description: str | None
    ip_address: str | None
    created_at: str


@router.get("/audit-logs", response_model=list[AuditLogItem])
def list_audit_logs(limit: int = 100, offset: int = 0, action_type: str | None = None, admin: User = Depends(require_admin)):
    with get_session() as session:
        q = session.query(AuditLog).order_by(AuditLog.created_at.desc())
        if action_type:
            q = q.filter(AuditLog.action_type == action_type)
        logs = q.offset(offset).limit(limit).all()
        return [
            AuditLogItem(
                log_id=l.log_id, user_id=l.user_id, action_type=l.action_type,
                target_type=l.target_type, description=l.description,
                ip_address=l.ip_address, created_at=l.created_at.isoformat(),
            )
            for l in logs
        ]


# --- LLM Config ---

class LLMConfigResponse(BaseModel):
    id: int
    model_name: str
    vllm_url: str
    system_prompt: str | None
    max_tokens: int
    temperature: float
    top_p: float
    context_chunks: int
    is_active: bool


class UpdateLLMConfigRequest(BaseModel):
    system_prompt: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    context_chunks: int | None = None


@router.get("/llm-config", response_model=LLMConfigResponse)
def get_llm_config(admin: User = Depends(require_admin)):
    with get_session() as session:
        config = session.query(LLMConfig).filter(LLMConfig.is_active == True).first()
        if not config:
            raise HTTPException(status_code=404, detail="No active LLM config")
        return LLMConfigResponse(
            id=config.id, model_name=config.model_name, vllm_url=config.vllm_url,
            system_prompt=config.system_prompt, max_tokens=config.max_tokens,
            temperature=config.temperature, top_p=config.top_p,
            context_chunks=config.context_chunks, is_active=config.is_active,
        )


@router.patch("/llm-config/{config_id}", response_model=LLMConfigResponse)
def update_llm_config(config_id: int, req: UpdateLLMConfigRequest, admin: User = Depends(require_admin)):
    with get_session() as session:
        config = session.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            raise HTTPException(status_code=404, detail="Config not found")

        if req.system_prompt is not None:
            config.system_prompt = req.system_prompt
        if req.max_tokens is not None:
            config.max_tokens = req.max_tokens
        if req.temperature is not None:
            config.temperature = req.temperature
        if req.top_p is not None:
            config.top_p = req.top_p
        if req.context_chunks is not None:
            config.context_chunks = req.context_chunks

        return LLMConfigResponse(
            id=config.id, model_name=config.model_name, vllm_url=config.vllm_url,
            system_prompt=config.system_prompt, max_tokens=config.max_tokens,
            temperature=config.temperature, top_p=config.top_p,
            context_chunks=config.context_chunks, is_active=config.is_active,
        )


# --- Query Logs ---

class QueryLogItem(BaseModel):
    id: int
    user_id: int | None
    session_id: int | None
    prompt: str
    model_name: str | None
    latency_ms: int | None
    created_at: str


@router.get("/queries", response_model=list[QueryLogItem])
def list_query_logs(
    limit: int = 50,
    offset: int = 0,
    user_id: int | None = None,
    date_from: str | None = Query(None, description="ISO date, e.g. 2026-01-01"),
    date_to: str | None = Query(None, description="ISO date, e.g. 2026-12-31"),
    admin: User = Depends(require_admin),
):
    with get_session() as session:
        q = session.query(QueryLog).order_by(QueryLog.created_at.desc())
        if user_id is not None:
            q = q.filter(QueryLog.user_id == user_id)
        if date_from:
            q = q.filter(QueryLog.created_at >= date_from)
        if date_to:
            q = q.filter(QueryLog.created_at <= date_to)
        logs = q.offset(offset).limit(limit).all()
        return [
            QueryLogItem(
                id=l.id, user_id=l.user_id, session_id=l.session_id,
                prompt=l.prompt[:200], model_name=l.model_name,
                latency_ms=l.latency_ms, created_at=l.created_at.isoformat(),
            )
            for l in logs
        ]


# --- Pipeline Logs ---

class PipelineLogItem(BaseModel):
    id: int
    doc_id: int | None
    stage: str
    status: str
    started_at: str | None
    finished_at: str | None
    error_message: str | None


@router.get("/pipeline-logs", response_model=list[PipelineLogItem])
def list_pipeline_logs(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    stage: str | None = None,
    admin: User = Depends(require_admin),
):
    with get_session() as session:
        q = session.query(PipelineLog).order_by(PipelineLog.started_at.desc())
        if status:
            q = q.filter(PipelineLog.status == status)
        if stage:
            q = q.filter(PipelineLog.stage == stage)
        logs = q.offset(offset).limit(limit).all()
        return [
            PipelineLogItem(
                id=l.id, doc_id=l.doc_id, stage=l.stage, status=l.status,
                started_at=l.started_at.isoformat() if l.started_at else None,
                finished_at=l.finished_at.isoformat() if l.finished_at else None,
                error_message=l.error_message,
            )
            for l in logs
        ]


# --- Stats ---

class DailyStatItem(BaseModel):
    date: str
    query_count: int
    avg_latency_ms: float | None


@router.get("/stats/daily", response_model=list[DailyStatItem])
def daily_stats(days: int = 30, admin: User = Depends(require_admin)):
    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT DATE(created_at) AS dt,
                       COUNT(*) AS cnt,
                       AVG(latency_ms) AS avg_lat
                FROM query_logs
                WHERE created_at >= NOW() - INTERVAL ':days days'
                GROUP BY DATE(created_at)
                ORDER BY dt DESC
            """.replace(":days", str(int(days))))
        ).fetchall()
        return [
            DailyStatItem(
                date=str(r.dt),
                query_count=r.cnt,
                avg_latency_ms=round(r.avg_lat, 1) if r.avg_lat else None,
            )
            for r in rows
        ]


class FileStatusStat(BaseModel):
    status: str
    count: int


@router.get("/stats/files", response_model=list[FileStatusStat])
def file_status_stats(admin: User = Depends(require_admin)):
    with get_session() as session:
        rows = (
            session.query(Document.status, func.count(Document.doc_id))
            .group_by(Document.status)
            .all()
        )
        return [FileStatusStat(status=r[0], count=r[1]) for r in rows]


class TopUserStat(BaseModel):
    user_id: int
    usr_name: str
    query_count: int


@router.get("/stats/top-users", response_model=list[TopUserStat])
def top_users(limit: int = 10, admin: User = Depends(require_admin)):
    with get_session() as session:
        rows = (
            session.query(
                QueryLog.user_id,
                func.count(QueryLog.id).label("cnt"),
            )
            .group_by(QueryLog.user_id)
            .order_by(func.count(QueryLog.id).desc())
            .limit(limit)
            .all()
        )
        result = []
        for r in rows:
            user = session.query(User).filter(User.user_id == r.user_id).first()
            result.append(TopUserStat(
                user_id=r.user_id,
                usr_name=user.usr_name if user else "Unknown",
                query_count=r.cnt,
            ))
        return result
