import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, text

from rag_serving.api.auth.dependencies import get_current_user, require_admin
from rag_serving.api.auth.password import hash_password
from rag_serving.config import serving_settings
from shared.models.orm import (
    AuditLog, Department, DocBlock, DocChunk, DocFolder, DocImage, Document, EventLog,
    GraphEntity, LLMConfig, PipelineLog, QueryLog, Role, SyncLog, User,
)
from shared.db import get_session
from shared.event_logger import get_event_logger

elog = get_event_logger("admin")

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


class AdminDocumentListItem(BaseModel):
    doc_id: int
    file_name: str
    path: str
    type: str
    status: str
    language: str | None
    total_page_cnt: int
    size: int | None
    folder_name: str | None
    dept_name: str | None
    role_name: str | None
    block_count: int
    chunk_count: int
    image_count: int
    entity_count: int
    error_msg: str | None
    created_at: str
    updated_at: str


class PipelineLogItem(BaseModel):
    id: int
    doc_id: int | None
    doc_file_name: str | None = None
    stage: str
    status: str
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    metadata: dict | None = None


class AdminDocumentBlockItem(BaseModel):
    block_id: int
    block_idx: int
    block_type: str
    page_number: int | None
    sheet_name: str | None
    slide_number: int | None
    section_path: str | None
    language: str | None
    preview_text: str
    source_text: str
    image_id: int | None
    image_url: str | None
    metadata: dict | None = None


class AdminDocumentDetailResponse(AdminDocumentListItem):
    recent_pipeline_logs: list[PipelineLogItem]
    recent_blocks: list[AdminDocumentBlockItem]


def _document_base_query(session):
    chunk_counts = (
        session.query(
            DocChunk.doc_id.label("doc_id"),
            func.count(DocChunk.chunk_id).label("chunk_count"),
        )
        .group_by(DocChunk.doc_id)
        .subquery()
    )
    image_counts = (
        session.query(
            DocImage.doc_id.label("doc_id"),
            func.count(DocImage.image_id).label("image_count"),
        )
        .group_by(DocImage.doc_id)
        .subquery()
    )
    block_counts = (
        session.query(
            DocBlock.doc_id.label("doc_id"),
            func.count(DocBlock.block_id).label("block_count"),
        )
        .group_by(DocBlock.doc_id)
        .subquery()
    )
    entity_counts = (
        session.query(
            GraphEntity.doc_id.label("doc_id"),
            func.count(GraphEntity.id).label("entity_count"),
        )
        .group_by(GraphEntity.doc_id)
        .subquery()
    )

    return (
        session.query(
            Document.doc_id.label("doc_id"),
            Document.file_name.label("file_name"),
            Document.path.label("path"),
            Document.type.label("type"),
            Document.status.label("status"),
            Document.language.label("language"),
            Document.total_page_cnt.label("total_page_cnt"),
            Document.size.label("size"),
            DocFolder.folder_name.label("folder_name"),
            Department.name.label("dept_name"),
            Role.role_name.label("role_name"),
            func.coalesce(block_counts.c.block_count, 0).label("block_count"),
            func.coalesce(chunk_counts.c.chunk_count, 0).label("chunk_count"),
            func.coalesce(image_counts.c.image_count, 0).label("image_count"),
            func.coalesce(entity_counts.c.entity_count, 0).label("entity_count"),
            Document.error_msg.label("error_msg"),
            Document.created_at.label("created_at"),
            Document.updated_at.label("updated_at"),
        )
        .outerjoin(Department, Department.dept_id == Document.dept_id)
        .outerjoin(Role, Role.role_id == Document.role_id)
        .outerjoin(DocFolder, DocFolder.folder_id == Document.folder_id)
        .outerjoin(block_counts, block_counts.c.doc_id == Document.doc_id)
        .outerjoin(chunk_counts, chunk_counts.c.doc_id == Document.doc_id)
        .outerjoin(image_counts, image_counts.c.doc_id == Document.doc_id)
        .outerjoin(entity_counts, entity_counts.c.doc_id == Document.doc_id)
    )


def _serialize_document_row(row) -> AdminDocumentListItem:
    return AdminDocumentListItem(
        doc_id=row.doc_id,
        file_name=row.file_name,
        path=row.path,
        type=row.type,
        status=row.status,
        language=row.language,
        total_page_cnt=row.total_page_cnt or 0,
        size=row.size,
        folder_name=row.folder_name,
        dept_name=row.dept_name,
        role_name=row.role_name,
        block_count=row.block_count or 0,
        chunk_count=row.chunk_count or 0,
        image_count=row.image_count or 0,
        entity_count=row.entity_count or 0,
        error_msg=row.error_msg,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


def _serialize_block_row(row) -> AdminDocumentBlockItem:
    source_text = row.source_text or ""
    preview_text = source_text if len(source_text) <= 240 else source_text[:237] + "..."
    image_url = f"/api/v1/admin/images/{row.image_id}" if row.image_id else None
    return AdminDocumentBlockItem(
        block_id=row.block_id,
        block_idx=row.block_idx,
        block_type=row.block_type,
        page_number=row.page_number,
        sheet_name=row.sheet_name,
        slide_number=row.slide_number,
        section_path=row.section_path,
        language=row.language,
        preview_text=preview_text,
        source_text=source_text,
        image_id=row.image_id,
        image_url=image_url,
        metadata=row.metadata_json,
    )


@router.get("/documents/stats", response_model=DocStats)
def doc_stats(admin: User = Depends(require_admin)):
    with get_session() as session:
        return DocStats(
            total=session.query(Document).count(),
            indexed=session.query(Document).filter(Document.status == "indexed").count(),
            failed=session.query(Document).filter(Document.status == "failed").count(),
            pending=session.query(Document).filter(Document.status.in_(["pending", "processing"])).count(),
        )


@router.get("/documents", response_model=list[AdminDocumentListItem])
def list_documents(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    q: str | None = Query(None, description="file name or path search"),
    admin: User = Depends(require_admin),
):
    with get_session() as session:
        query = _document_base_query(session).order_by(Document.updated_at.desc())
        if status:
            query = query.filter(Document.status == status)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    Document.file_name.ilike(like),
                    Document.path.ilike(like),
                    Document.type.ilike(like),
                )
            )

        rows = query.offset(offset).limit(limit).all()
        return [_serialize_document_row(row) for row in rows]


@router.get("/documents/{doc_id}", response_model=AdminDocumentDetailResponse)
def get_document_detail(doc_id: int, admin: User = Depends(require_admin)):
    with get_session() as session:
        row = _document_base_query(session).filter(Document.doc_id == doc_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        logs = (
            session.query(PipelineLog, Document.file_name)
            .outerjoin(Document, Document.doc_id == PipelineLog.doc_id)
            .filter(PipelineLog.doc_id == doc_id)
            .order_by(PipelineLog.started_at.desc())
            .limit(10)
            .all()
        )
        blocks = (
            session.query(DocBlock)
            .filter(DocBlock.doc_id == doc_id)
            .order_by(DocBlock.block_idx.asc())
            .limit(24)
            .all()
        )

    item = _serialize_document_row(row)
    return AdminDocumentDetailResponse(
        **item.model_dump(),
        recent_pipeline_logs=[
            PipelineLogItem(
                id=log.id,
                doc_id=log.doc_id,
                doc_file_name=file_name,
                stage=log.stage,
                status=log.status,
                started_at=log.started_at.isoformat() if log.started_at else None,
                finished_at=log.finished_at.isoformat() if log.finished_at else None,
                error_message=log.error_message,
                metadata=log.metadata_,
            )
            for log, file_name in logs
        ],
        recent_blocks=[_serialize_block_row(block) for block in blocks],
    )


@router.get("/documents/{doc_id}/blocks", response_model=list[AdminDocumentBlockItem])
def list_document_blocks(
    doc_id: int,
    limit: int = 100,
    block_type: str | None = None,
    admin: User = Depends(require_admin),
):
    with get_session() as session:
        if not session.query(Document.doc_id).filter(Document.doc_id == doc_id).first():
            raise HTTPException(status_code=404, detail="Document not found")

        query = session.query(DocBlock).filter(DocBlock.doc_id == doc_id)
        if block_type:
            query = query.filter(DocBlock.block_type == block_type)
        blocks = query.order_by(DocBlock.block_idx.asc()).limit(limit).all()
        return [_serialize_block_row(block) for block in blocks]


@router.get("/images/{image_id}")
def get_document_image(image_id: int, admin: User = Depends(require_admin)):
    with get_session() as session:
        image = session.query(DocImage).filter(DocImage.image_id == image_id).first()
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        image_path = Path(image.image_path)

    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image file missing")

    media_type = f"image/{(image.image_type or image_path.suffix.lstrip('.')).lower()}"
    return FileResponse(str(image_path), media_type=media_type)


class RecentPipelineFailureItem(BaseModel):
    id: int
    doc_id: int | None
    doc_file_name: str | None = None
    stage: str
    error_message: str | None
    started_at: str | None


class RecentSyncRunItem(BaseModel):
    id: int
    sync_type: str | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    files_added: int
    files_modified: int
    files_deleted: int


class SystemSummaryResponse(BaseModel):
    documents: DocStats
    active_users_7d: int
    queries_7d: int
    recent_pipeline_failures: list[RecentPipelineFailureItem]
    recent_sync_runs: list[RecentSyncRunItem]
    pipeline_running_count: int
    event_errors_24h: int


@router.get("/system-summary", response_model=SystemSummaryResponse)
def system_summary(admin: User = Depends(require_admin)):
    with get_session() as session:
        latest_pipeline_log_ids = (
            session.query(func.max(PipelineLog.id).label("id"))
            .group_by(PipelineLog.doc_id, PipelineLog.stage)
            .subquery()
        )

        documents = DocStats(
            total=session.query(Document).count(),
            indexed=session.query(Document).filter(Document.status == "indexed").count(),
            failed=session.query(Document).filter(Document.status == "failed").count(),
            pending=session.query(Document).filter(Document.status.in_(["pending", "processing"])).count(),
        )
        active_users_7d = (
            session.query(func.count(func.distinct(QueryLog.user_id)))
            .filter(QueryLog.created_at >= func.now() - text("INTERVAL '7 days'"))
            .scalar()
            or 0
        )
        queries_7d = (
            session.query(func.count(QueryLog.id))
            .filter(QueryLog.created_at >= func.now() - text("INTERVAL '7 days'"))
            .scalar()
            or 0
        )
        pipeline_running_count = (
            session.query(func.count(PipelineLog.id))
            .filter(
                PipelineLog.id.in_(session.query(latest_pipeline_log_ids.c.id)),
                PipelineLog.status == "running",
                PipelineLog.finished_at.is_(None),
            )
            .scalar()
            or 0
        )
        event_errors_24h = (
            session.query(func.count(EventLog.id))
            .filter(
                EventLog.severity == "error",
                EventLog.created_at >= func.now() - text("INTERVAL '24 hours'"),
            )
            .scalar()
            or 0
        )

        recent_failures = (
            session.query(PipelineLog, Document.file_name)
            .outerjoin(Document, Document.doc_id == PipelineLog.doc_id)
            .filter(PipelineLog.status == "failed")
            .order_by(PipelineLog.started_at.desc())
            .limit(5)
            .all()
        )
        recent_syncs = (
            session.query(SyncLog)
            .order_by(SyncLog.started_at.desc())
            .limit(5)
            .all()
        )

    return SystemSummaryResponse(
        documents=documents,
        active_users_7d=active_users_7d,
        queries_7d=queries_7d,
        recent_pipeline_failures=[
            RecentPipelineFailureItem(
                id=log.id,
                doc_id=log.doc_id,
                doc_file_name=file_name,
                stage=log.stage,
                error_message=log.error_message,
                started_at=log.started_at.isoformat() if log.started_at else None,
            )
            for log, file_name in recent_failures
        ],
        recent_sync_runs=[
            RecentSyncRunItem(
                id=item.id,
                sync_type=item.sync_type,
                status=item.status,
                started_at=item.started_at.isoformat() if item.started_at else None,
                finished_at=item.finished_at.isoformat() if item.finished_at else None,
                files_added=item.files_added or 0,
                files_modified=item.files_modified or 0,
                files_deleted=item.files_deleted or 0,
            )
            for item in recent_syncs
        ],
        pipeline_running_count=pipeline_running_count,
        event_errors_24h=event_errors_24h,
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
            id=config.id,
            model_name=serving_settings.vllm_model_name if serving_settings.prefer_env_llm_config else config.model_name,
            vllm_url=serving_settings.vllm_base_url if serving_settings.prefer_env_llm_config else config.vllm_url,
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
            id=config.id,
            model_name=serving_settings.vllm_model_name if serving_settings.prefer_env_llm_config else config.model_name,
            vllm_url=serving_settings.vllm_base_url if serving_settings.prefer_env_llm_config else config.vllm_url,
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


@router.get("/pipeline-logs", response_model=list[PipelineLogItem])
def list_pipeline_logs(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    stage: str | None = None,
    admin: User = Depends(require_admin),
):
    with get_session() as session:
        q = (
            session.query(PipelineLog, Document.file_name)
            .outerjoin(Document, Document.doc_id == PipelineLog.doc_id)
            .order_by(PipelineLog.started_at.desc())
        )
        if status:
            q = q.filter(PipelineLog.status == status)
        if stage:
            q = q.filter(PipelineLog.stage == stage)
        logs = q.offset(offset).limit(limit).all()
        return [
            PipelineLogItem(
                id=log.id,
                doc_id=log.doc_id,
                doc_file_name=file_name,
                stage=log.stage,
                status=log.status,
                started_at=log.started_at.isoformat() if log.started_at else None,
                finished_at=log.finished_at.isoformat() if log.finished_at else None,
                error_message=log.error_message,
                metadata=log.metadata_,
            )
            for log, file_name in logs
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


# --- Event Logs (general-purpose, all modules) ---

class EventLogItem(BaseModel):
    id: int
    trace_id: str | None
    module: str
    event_type: str
    severity: str
    user_id: int | None
    session_id: int | None
    doc_id: int | None
    message: str
    details: dict | None
    duration_ms: int | None
    ip_address: str | None
    created_at: str


@router.get("/event-logs", response_model=list[EventLogItem])
def list_event_logs(
    limit: int = 50,
    offset: int = 0,
    module: str | None = Query(None, description="Filter by module: pipeline, serving, sync, system, admin"),
    event_type: str | None = Query(None, description="Filter by event_type: info, error, stage_start, stage_end, etc."),
    severity: str | None = Query(None, description="Filter by severity: debug, info, warning, error, critical"),
    trace_id: str | None = Query(None, description="Filter by trace_id for request correlation"),
    doc_id: int | None = Query(None, description="Filter by document ID"),
    user_id: int | None = Query(None, description="Filter by user ID"),
    admin_user: User = Depends(require_admin),
):
    with get_session() as session:
        q = session.query(EventLog).order_by(EventLog.created_at.desc())
        if module:
            q = q.filter(EventLog.module == module)
        if event_type:
            q = q.filter(EventLog.event_type == event_type)
        if severity:
            q = q.filter(EventLog.severity == severity)
        if trace_id:
            q = q.filter(EventLog.trace_id == trace_id)
        if doc_id:
            q = q.filter(EventLog.doc_id == doc_id)
        if user_id:
            q = q.filter(EventLog.user_id == user_id)
        logs = q.offset(offset).limit(limit).all()
        return [
            EventLogItem(
                id=l.id, trace_id=l.trace_id, module=l.module,
                event_type=l.event_type, severity=l.severity,
                user_id=l.user_id, session_id=l.session_id, doc_id=l.doc_id,
                message=l.message, details=l.details,
                duration_ms=l.duration_ms, ip_address=l.ip_address,
                created_at=l.created_at.isoformat(),
            )
            for l in logs
        ]


# --- Sync Logs ---

class SyncLogItem(BaseModel):
    id: int
    sync_type: str | None
    started_at: str | None
    finished_at: str | None
    files_added: int
    files_modified: int
    files_deleted: int
    users_added: int
    status: str | None
    error_message: str | None


@router.get("/sync-logs", response_model=list[SyncLogItem])
def list_sync_logs(
    limit: int = 50,
    offset: int = 0,
    sync_type: str | None = None,
    status: str | None = None,
    admin_user: User = Depends(require_admin),
):
    with get_session() as session:
        q = session.query(SyncLog).order_by(SyncLog.started_at.desc())
        if sync_type:
            q = q.filter(SyncLog.sync_type == sync_type)
        if status:
            q = q.filter(SyncLog.status == status)
        logs = q.offset(offset).limit(limit).all()
        return [
            SyncLogItem(
                id=l.id, sync_type=l.sync_type,
                started_at=l.started_at.isoformat() if l.started_at else None,
                finished_at=l.finished_at.isoformat() if l.finished_at else None,
                files_added=l.files_added or 0, files_modified=l.files_modified or 0,
                files_deleted=l.files_deleted or 0, users_added=l.users_added or 0,
                status=l.status, error_message=l.error_message,
            )
            for l in logs
        ]


# --- Module Stats (aggregated from event_log) ---

class ModuleStatItem(BaseModel):
    module: str
    total_events: int
    errors: int
    warnings: int
    avg_duration_ms: float | None


@router.get("/stats/modules", response_model=list[ModuleStatItem])
def module_stats(days: int = 7, admin_user: User = Depends(require_admin)):
    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT module,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE severity = 'error') AS errors,
                       COUNT(*) FILTER (WHERE severity = 'warning') AS warnings,
                       AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL) AS avg_dur
                FROM event_log
                WHERE created_at >= NOW() - INTERVAL ':days days'
                GROUP BY module
                ORDER BY total DESC
            """.replace(":days", str(int(days))))
        ).fetchall()
        return [
            ModuleStatItem(
                module=r.module,
                total_events=r.total,
                errors=r.errors,
                warnings=r.warnings,
                avg_duration_ms=round(r.avg_dur, 1) if r.avg_dur else None,
            )
            for r in rows
        ]
