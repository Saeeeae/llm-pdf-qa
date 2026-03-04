import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, require_admin
from app.auth.password import hash_password
from app.db.models import AuditLog, Department, Document, LLMConfig, Role, SystemHealth, User
from app.db.postgres import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


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

        if req.usr_name is not None: user.usr_name = req.usr_name
        if req.dept_id is not None: user.dept_id = req.dept_id
        if req.role_id is not None: user.role_id = req.role_id
        if req.is_active is not None: user.is_active = req.is_active
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

        if req.system_prompt is not None: config.system_prompt = req.system_prompt
        if req.max_tokens is not None: config.max_tokens = req.max_tokens
        if req.temperature is not None: config.temperature = req.temperature
        if req.top_p is not None: config.top_p = req.top_p
        if req.context_chunks is not None: config.context_chunks = req.context_chunks

        return LLMConfigResponse(
            id=config.id, model_name=config.model_name, vllm_url=config.vllm_url,
            system_prompt=config.system_prompt, max_tokens=config.max_tokens,
            temperature=config.temperature, top_p=config.top_p,
            context_chunks=config.context_chunks, is_active=config.is_active,
        )
