# RAG-LLM Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 기존 RAG 전처리 파이프라인 위에 인증 + RAG-LLM 채팅 + 웹검색 + Admin API + Next.js 프론트를 추가하여 완전 온프레미스 사내 AI 어시스턴트 구축

**Architecture:** FastAPI 단일 백엔드 확장 (auth/chat/admin 라우터 추가) + vLLM(Qwen2.5-72B-AWQ) + Next.js 프론트엔드. 기존 동기 SQLAlchemy 세션 패턴 유지. SSE 스트리밍으로 ChatGPT 수준 UX 구현.

**Tech Stack:** FastAPI, SQLAlchemy(sync), python-jose(JWT), passlib(bcrypt), httpx(vLLM SSE), Next.js 14(App Router), TypeScript, Tailwind CSS, SearXNG(자체호스팅 웹검색), Docker Compose

**Design Doc:** `docs/plans/2026-03-04-rag-llm-service-design.md`

---

## Phase 1: 인증 시스템

### Task 1: DB 마이그레이션 — 신규 테이블 추가

**Files:**
- Modify: `app/db/init_schema.sql` (신규 테이블 추가)
- Modify: `app/db/models.py` (신규 ORM 모델 추가)

**Step 1: init_schema.sql 에 신규 테이블 4개 추가**

`app/db/init_schema.sql` 파일 맨 끝 (기존 Views 섹션 이전)에 추가:

```sql
-- =============================================================================
-- 20. Refresh Token
-- =============================================================================
CREATE TABLE IF NOT EXISTS refresh_token (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45)
);
CREATE INDEX IF NOT EXISTS idx_refresh_token_user ON refresh_token(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_token_hash ON refresh_token(token_hash);

-- =============================================================================
-- 21. User Preference
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_preference (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    preferences JSONB DEFAULT '{"search_scope": "all", "web_search": false, "theme": "light"}'
);

-- =============================================================================
-- 22. LLM Config (Admin 관리)
-- =============================================================================
CREATE TABLE IF NOT EXISTS llm_config (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    vllm_url VARCHAR(255) NOT NULL DEFAULT 'http://vllm-server:8001/v1',
    system_prompt TEXT DEFAULT '당신은 사내 문서를 기반으로 답변하는 AI 어시스턴트입니다. 제공된 문서 내용을 바탕으로 정확하고 도움이 되는 답변을 제공하세요.',
    max_tokens INTEGER DEFAULT 4096,
    temperature FLOAT DEFAULT 0.7,
    top_p FLOAT DEFAULT 0.9,
    context_chunks INTEGER DEFAULT 5,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 23. Web Search Log
-- =============================================================================
CREATE TABLE IF NOT EXISTS web_search_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES chat_session(session_id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    was_blocked BOOLEAN DEFAULT FALSE,
    block_reason TEXT,
    results_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_web_search_log_user ON web_search_log(user_id);

-- Seed: default LLM config
INSERT INTO llm_config (model_name, vllm_url) VALUES
    ('qwen2.5-72b', 'http://vllm-server:8001/v1')
    ON CONFLICT DO NOTHING;
```

**Step 2: models.py 에 ORM 모델 추가**

`app/db/models.py` 파일 끝에 추가:

```python
class RefreshToken(Base):
    __tablename__ = "refresh_token"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(Text, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ip_address = Column(String(45))

    user = relationship("User")


class UserPreference(Base):
    __tablename__ = "user_preference"

    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    preferences = Column(JSON, default=lambda: {"search_scope": "all", "web_search": False, "theme": "light"})

    user = relationship("User")


class LLMConfig(Base):
    __tablename__ = "llm_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False)
    vllm_url = Column(String(255), nullable=False, default="http://vllm-server:8001/v1")
    system_prompt = Column(Text)
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
    creator = relationship("User")


class ChatMessage(Base):
    __tablename__ = "chat_msg"

    msg_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_session.session_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"))
    sender_type = Column(String(10), nullable=False)  # 'user' | 'assistant'
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
```

**Step 3: Workspace 모델 추가** (chat_session이 참조)

`app/db/models.py`의 `ChatSession` 앞에 추가:

```python
class Workspace(Base):
    __tablename__ = "workspace"

    ws_id = Column(Integer, primary_key=True, autoincrement=True)
    ws_name = Column(String(200), nullable=False)
    owner_dept_id = Column(Integer, ForeignKey("department.dept_id", ondelete="RESTRICT"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
```

**Step 4: DB 재초기화 (개발환경)**

```bash
cd /Users/sae/Desktop/llm_again
docker compose down -v --remove-orphans
make up
# 잠시 대기 후 확인
docker compose exec postgres psql -U admin -d rag_system -c "\dt"
```

Expected: `refresh_token`, `user_preference`, `llm_config`, `web_search_log` 테이블 확인

**Step 5: Commit**

```bash
git add app/db/init_schema.sql app/db/models.py
git commit -m "feat: add auth/chat/llm DB schema and ORM models"
```

---

### Task 2: JWT 인증 유틸리티

**Files:**
- Create: `app/auth/__init__.py`
- Create: `app/auth/jwt.py`
- Create: `app/auth/password.py`
- Create: `app/auth/dependencies.py`

**Step 1: requirements 에 JWT/bcrypt 패키지 추가**

`requirements/api.txt`:
```
-r base.txt
-r torch-gpu.txt

# API
fastapi==0.115.12
uvicorn[standard]==0.34.0
python-multipart==0.0.20

# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
```

**Step 2: `app/auth/__init__.py` 생성**

```python
# empty
```

**Step 3: `app/auth/password.py` 생성**

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

**Step 4: `app/config.py` 에 JWT 설정 추가**

`app/config.py`의 `Settings` 클래스에 추가:

```python
    # JWT
    jwt_secret: str = "CHANGE_THIS_SECRET_IN_PRODUCTION_MIN_32_CHARS"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7
```

**Step 5: `app/auth/jwt.py` 생성**

```python
import hashlib
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings


def create_access_token(user_id: int, role_auth_level: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload = {
        "sub": str(user_id),
        "auth_level": role_auth_level,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Raises JWTError if invalid or expired."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
```

**Step 6: `app/auth/dependencies.py` 생성**

```python
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import decode_token
from app.db.models import User, Role
from app.db.postgres import get_session

bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")

    user_id = int(payload["sub"])
    with get_session() as session:
        user = session.query(User).filter(User.user_id == user_id, User.is_active == True).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        # Detach from session to return
        session.expunge(user)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    with get_session() as session:
        role = session.query(Role).filter(Role.role_id == user.role_id).first()
    if not role or role.auth_level < 100:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user
```

**Step 7: Commit**

```bash
git add app/auth/ app/config.py requirements/api.txt
git commit -m "feat: add JWT auth utilities and password hashing"
```

---

### Task 3: Auth API 라우터

**Files:**
- Create: `app/api/routes/auth.py`
- Modify: `app/api/main.py`

**Step 1: `app/api/routes/auth.py` 생성**

```python
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token, create_refresh_token, decode_token, hash_token
from app.auth.password import verify_password
from app.db.models import RefreshToken, Role, User, UserPreference
from app.db.postgres import get_session
from app.config import settings

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


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request):
    ip = request.client.host if request.client else None

    with get_session() as session:
        user = session.query(User).filter(User.email == req.email).first()

        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # 계정 잠금 확인
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account locked")

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

        if not verify_password(req.password, user.pwd):
            user.failure = (user.failure or 0) + 1
            if user.failure >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # 로그인 성공 — 실패 횟수 초기화
        user.failure = 0
        user.last_login = datetime.now(timezone.utc)

        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        from app.db.models import Department
        dept = session.query(Department).filter(Department.dept_id == user.dept_id).first()

        access_token = create_access_token(user.user_id, role.auth_level)
        refresh_token_str = create_refresh_token(user.user_id)

        # 리프레시 토큰 저장
        rt = RefreshToken(
            user_id=user.user_id,
            token_hash=hash_token(refresh_token_str),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days),
            ip_address=ip,
        )
        session.add(rt)

        # user_preference 없으면 생성
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


class MeResponse(BaseModel):
    user_id: int
    usr_name: str
    email: str
    role_name: str
    auth_level: int
    dept_name: str
    preferences: dict


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    with get_session() as session:
        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        from app.db.models import Department
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
```

**Step 2: `app/api/main.py` 에 auth 라우터 등록**

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import documents, processing, health, images, auth

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RAG Preprocessing API")
    yield
    logger.info("Shutting down RAG Preprocessing API")


app = FastAPI(
    title="사내 AI 어시스턴트 API",
    description="RAG 문서 전처리 + LLM 채팅 + 관리자 API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(processing.router, prefix="/api/v1/processing", tags=["Processing"])
app.include_router(images.router, prefix="/api/v1", tags=["Images"])
```

**Step 3: 테스트 — 로그인 API 동작 확인**

먼저 테스트 유저를 DB에 직접 생성:
```bash
# bcrypt 해시 생성 (python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('test1234'))")
docker compose exec postgres psql -U admin -d rag_system -c "
INSERT INTO users (pwd, usr_name, email, dept_id, role_id) VALUES
('\$2b\$12\$...해시값...', '테스트관리자', 'admin@company.com', 1, 1)
ON CONFLICT DO NOTHING;"
```

실제로는 아래 스크립트로:
```bash
docker compose exec api python3 -c "
from app.auth.password import hash_password
from app.db.models import User
from app.db.postgres import get_session
with get_session() as s:
    u = User(pwd=hash_password('test1234'), usr_name='관리자', email='admin@company.com', dept_id=1, role_id=1)
    s.add(u)
print('created')
"
```

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.com","password":"test1234"}'
```

Expected: `{ "access_token": "...", "refresh_token": "...", "usr_name": "관리자" }`

**Step 4: Commit**

```bash
git add app/api/routes/auth.py app/api/main.py
git commit -m "feat: add JWT login/refresh/logout/me auth API"
```

---

## Phase 2: RAG-LLM Chat 서비스

### Task 4: vLLM Docker 서비스 설정

**Files:**
- Create: `Dockerfile.vllm`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1: `Dockerfile.vllm` 생성**

```dockerfile
FROM vllm/vllm-openai:latest

# vLLM은 이미 필요한 모든 것을 포함
# 모델은 볼륨 마운트로 제공하거나 HuggingFace에서 자동 다운로드
EXPOSE 8001
```

**Step 2: `docker-compose.yml` 에 vllm-server 서비스 추가**

기존 서비스들 뒤에 추가:

```yaml
  vllm-server:
    image: vllm/vllm-openai:latest
    container_name: rag-vllm
    command: >
      python -m vllm.entrypoints.openai.api_server
      --model ${VLLM_MODEL:-Qwen/Qwen2.5-72B-Instruct-AWQ}
      --quantization ${VLLM_QUANTIZATION:-awq}
      --tensor-parallel-size ${VLLM_TENSOR_PARALLEL:-1}
      --gpu-memory-utilization ${VLLM_GPU_MEM_UTIL:-0.90}
      --max-model-len ${VLLM_MAX_MODEL_LEN:-32768}
      --served-model-name ${VLLM_SERVED_MODEL_NAME:-qwen2.5-72b}
      --host 0.0.0.0
      --port 8001
    ports:
      - "8001:8001"
    environment:
      - HF_TOKEN=${HF_TOKEN}
    volumes:
      - ${VLLM_MODEL_DIR:-/data/models/vllm}:/root/.cache/huggingface
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: ${VLLM_GPU_COUNT:-1}
              capabilities: [gpu]
    restart: unless-stopped

  searxng:
    image: searxng/searxng:latest
    container_name: rag-searxng
    environment:
      - SEARXNG_SECRET=${SEARXNG_SECRET:-changethissecret}
    volumes:
      - ./searxng:/etc/searxng
    ports:
      - "8080:8080"
    restart: unless-stopped
```

**Step 3: `.env.example` 에 vLLM 변수 추가**

```ini
# vLLM
VLLM_MODEL=Qwen/Qwen2.5-72B-Instruct-AWQ
VLLM_QUANTIZATION=awq
VLLM_TENSOR_PARALLEL=1
VLLM_GPU_MEM_UTIL=0.90
VLLM_MAX_MODEL_LEN=32768
VLLM_SERVED_MODEL_NAME=qwen2.5-72b
VLLM_MODEL_DIR=/data/models/vllm
VLLM_GPU_COUNT=1

# SearXNG
SEARXNG_SECRET=changethissecret
```

**Step 4: SearXNG 설정 파일 생성**

```bash
mkdir -p /Users/sae/Desktop/llm_again/searxng
```

`searxng/settings.yml` 생성:

```yaml
use_default_settings: true
server:
  secret_key: "${SEARXNG_SECRET}"
  limiter: false
  image_proxy: false
search:
  safe_search: 0
  autocomplete: ""
  default_lang: "ko"
engines:
  - name: google
    engine: google
    shortcut: g
    use_mobile_ui: false
  - name: bing
    engine: bing
    shortcut: b
ui:
  default_theme: simple
  results_on_new_tab: false
```

**Step 5: Commit**

```bash
git add Dockerfile.vllm docker-compose.yml .env.example searxng/
git commit -m "feat: add vLLM and SearXNG docker services"
```

---

### Task 5: RBAC 적용 벡터 검색

**Files:**
- Modify: `app/db/vector_store.py`

**Step 1: `vector_store.py` 에 RBAC 필터 추가**

기존 `search_similar` 함수를 교체:

```python
def search_similar(
    query_vector: list[float],
    limit: int = 5,
    doc_id_filter: int | None = None,
    user_dept_id: int | None = None,
    user_auth_level: int | None = None,
    accessible_folder_ids: list[int] | None = None,
    search_scope: str = "all",  # "all" | "dept" | "folder"
) -> list[dict]:
    """Cosine similarity search with RBAC filtering.

    - search_scope="all": role auth_level 기반 필터만 적용
    - search_scope="dept": 사용자 부서 문서만 검색
    - search_scope="folder": accessible_folder_ids 내 문서만 검색
    """
    params: dict = {"vec": query_vector, "lim": limit}

    conditions = ["dc.embedding IS NOT NULL", "d.status = 'indexed'"]

    # RBAC: 사용자 auth_level 이상 필요한 문서 제외
    if user_auth_level is not None:
        conditions.append("r.auth_level <= :auth_level")
        params["auth_level"] = user_auth_level

    # 검색 범위
    if search_scope == "dept" and user_dept_id is not None:
        conditions.append("d.dept_id = :dept_id")
        params["dept_id"] = user_dept_id
    elif search_scope == "folder" and accessible_folder_ids:
        conditions.append("d.folder_id = ANY(:folder_ids)")
        params["folder_ids"] = accessible_folder_ids

    if doc_id_filter is not None:
        conditions.append("dc.doc_id = :did")
        params["did"] = doc_id_filter

    where_clause = "WHERE " + " AND ".join(conditions)

    sql = text(f"""
        SELECT
            dc.chunk_id,
            dc.doc_id,
            dc.chunk_idx,
            dc.content,
            dc.chunk_type,
            dc.page_number,
            1 - (dc.embedding <=> :vec::vector) AS score,
            d.file_name,
            di.image_id,
            di.image_path,
            di.image_type
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
        JOIN roles r ON d.role_id = r.role_id
        LEFT JOIN doc_image di ON dc.image_id = di.image_id
        {where_clause}
        ORDER BY dc.embedding <=> :vec::vector
        LIMIT :lim
    """)

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()

    return [
        {
            "chunk_id": r.chunk_id,
            "doc_id": r.doc_id,
            "chunk_idx": r.chunk_idx,
            "text": r.content[:500],
            "chunk_type": r.chunk_type or "text",
            "page_number": r.page_number,
            "score": float(r.score),
            "file_name": r.file_name,
            "image_id": r.image_id,
            "image_path": r.image_path,
        }
        for r in rows
    ]
```

**Step 2: Commit**

```bash
git add app/db/vector_store.py
git commit -m "feat: add RBAC filtering to vector search"
```

---

### Task 6: Chat API — 세션 CRUD + SSE 스트리밍

**Files:**
- Create: `app/api/routes/chat.py`
- Create: `app/chat/__init__.py`
- Create: `app/chat/rag_pipeline.py`
- Modify: `app/api/main.py`

**Step 1: `app/chat/__init__.py` 생성**

```python
# empty
```

**Step 2: `app/chat/rag_pipeline.py` 생성**

```python
"""RAG 파이프라인: 쿼리 → 벡터 검색 → 프롬프트 빌드 → vLLM 스트리밍."""

import json
import logging
from typing import Generator

import httpx

from app.config import settings
from app.db.models import LLMConfig, Role, FolderAccess
from app.db.postgres import get_session
from app.db.vector_store import search_similar
from app.processing.embedder import embed_query

logger = logging.getLogger(__name__)

# 사용자 권한으로 접근 가능한 folder_id 목록 조회
def get_accessible_folder_ids(user_id: int) -> list[int]:
    from app.db.models import FolderAccess
    with get_session() as session:
        try:
            rows = session.execute(
                __import__("sqlalchemy").text(
                    "SELECT folder_id FROM folder_access "
                    "WHERE user_id = :uid AND is_active = TRUE "
                    "AND (expires_at IS NULL OR expires_at > NOW())"
                ),
                {"uid": user_id},
            ).fetchall()
            return [r.folder_id for r in rows]
        except Exception:
            return []


def get_active_llm_config() -> LLMConfig:
    with get_session() as session:
        config = session.query(LLMConfig).filter(LLMConfig.is_active == True).first()
        if not config:
            # 기본값 반환
            return LLMConfig(
                model_name="qwen2.5-72b",
                vllm_url=settings.vllm_api_url,
                system_prompt="당신은 사내 문서를 기반으로 답변하는 AI 어시스턴트입니다.",
                max_tokens=4096,
                temperature=0.7,
                top_p=0.9,
                context_chunks=5,
            )
        session.expunge(config)
        return config


def retrieve_context(
    query: str,
    user_id: int,
    user_dept_id: int,
    user_auth_level: int,
    search_scope: str = "all",
    limit: int = 5,
) -> list[dict]:
    """쿼리에 관련된 문서 청크를 RBAC 필터링과 함께 검색."""
    query_vector = embed_query(query).tolist()
    accessible_folders = get_accessible_folder_ids(user_id)

    return search_similar(
        query_vector=query_vector,
        limit=limit,
        user_dept_id=user_dept_id,
        user_auth_level=user_auth_level,
        accessible_folder_ids=accessible_folders,
        search_scope=search_scope,
    )


def build_messages(
    system_prompt: str,
    context_chunks: list[dict],
    chat_history: list[dict],  # [{"role": "user"|"assistant", "content": "..."}]
    user_message: str,
) -> list[dict]:
    """vLLM OpenAI 형식 메시지 리스트 구성."""
    # 컨텍스트 블록 구성
    if context_chunks:
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            context_parts.append(
                f"[문서 {i}: {chunk['file_name']}"
                + (f" p.{chunk['page_number']}" if chunk.get("page_number") else "")
                + f"]\n{chunk['text']}"
            )
        context_text = "\n\n".join(context_parts)
        system_with_context = (
            f"{system_prompt}\n\n"
            f"=== 관련 문서 ===\n{context_text}\n"
            f"=== 문서 끝 ===\n\n"
            "위 문서를 참고하여 답변하세요. 문서에 없는 내용은 그렇다고 알려주세요."
        )
    else:
        system_with_context = system_prompt

    messages = [{"role": "system", "content": system_with_context}]

    # 대화 히스토리 (최근 10턴)
    for msg in chat_history[-20:]:
        messages.append(msg)

    messages.append({"role": "user", "content": user_message})
    return messages


def stream_llm_response(
    messages: list[dict],
    config: LLMConfig,
) -> Generator[str, None, None]:
    """vLLM SSE 스트리밍. 각 토큰을 yield."""
    payload = {
        "model": config.model_name,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "stream": True,
    }

    with httpx.Client(timeout=120.0) as client:
        with client.stream(
            "POST",
            f"{config.vllm_url}/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        continue
```

**Step 3: `app/api/routes/chat.py` 생성**

```python
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.chat.rag_pipeline import (
    build_messages,
    get_active_llm_config,
    retrieve_context,
    stream_llm_response,
)
from app.db.models import (
    AuditLog, ChatMessage, ChatSession, MsgRef, Role, User, UserPreference,
)
from app.db.postgres import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    session_id: int
    title: str | None
    created_at: str
    message_count: int = 0


class MessageResponse(BaseModel):
    msg_id: int
    sender_type: str
    message: str
    created_at: str


class ChatRequest(BaseModel):
    message: str
    search_scope: str = "all"  # all | dept | folder
    use_web_search: bool = False


@router.post("/sessions", response_model=SessionResponse)
def create_session(
    req: CreateSessionRequest,
    user: User = Depends(get_current_user),
):
    with get_session() as session:
        chat_session = ChatSession(
            created_by=user.user_id,
            title=req.title,
            session_type="private",
        )
        session.add(chat_session)
        session.flush()
        result = SessionResponse(
            session_id=chat_session.session_id,
            title=chat_session.title,
            created_at=chat_session.created_at.isoformat(),
        )
    return result


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_user),
):
    with get_session() as session:
        sessions = (
            session.query(ChatSession)
            .filter(ChatSession.created_by == user.user_id)
            .order_by(ChatSession.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            SessionResponse(
                session_id=s.session_id,
                title=s.title,
                created_at=s.created_at.isoformat(),
                message_count=len(s.messages),
            )
            for s in sessions
        ]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def get_messages(
    session_id: int,
    user: User = Depends(get_current_user),
):
    with get_session() as session:
        chat_session = session.query(ChatSession).filter(
            ChatSession.session_id == session_id,
            ChatSession.created_by == user.user_id,
        ).first()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        return [
            MessageResponse(
                msg_id=m.msg_id,
                sender_type=m.sender_type,
                message=m.message,
                created_at=m.created_at.isoformat(),
            )
            for m in sorted(chat_session.messages, key=lambda x: x.created_at)
        ]


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
):
    with get_session() as session:
        chat_session = session.query(ChatSession).filter(
            ChatSession.session_id == session_id,
            ChatSession.created_by == user.user_id,
        ).first()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")
        session.delete(chat_session)


@router.post("/sessions/{session_id}/stream")
def stream_chat(
    session_id: int,
    req: ChatRequest,
    user: User = Depends(get_current_user),
):
    """SSE 스트리밍 채팅 엔드포인트."""
    # 세션 소유권 확인
    with get_session() as session:
        chat_session = session.query(ChatSession).filter(
            ChatSession.session_id == session_id,
            ChatSession.created_by == user.user_id,
        ).first()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        # 이전 대화 히스토리 (최근 20개)
        messages_history = sorted(chat_session.messages, key=lambda x: x.created_at)[-20:]
        history = [
            {"role": m.sender_type, "content": m.message}
            for m in messages_history
        ]

        # 사용자 auth_level 조회
        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        auth_level = role.auth_level if role else 0

    def generate():
        full_response = ""
        context_chunks = []

        try:
            # 1. RAG 검색
            context_chunks = retrieve_context(
                query=req.message,
                user_id=user.user_id,
                user_dept_id=user.dept_id,
                user_auth_level=auth_level,
                search_scope=req.search_scope,
            )

            # 2. LLM 설정 로드
            llm_config = get_active_llm_config()

            # 3. 프롬프트 구성
            llm_messages = build_messages(
                system_prompt=llm_config.system_prompt or "",
                context_chunks=context_chunks,
                chat_history=history,
                user_message=req.message,
            )

            # 4. 스트리밍 토큰 전송
            for token in stream_llm_response(llm_messages, llm_config):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # 5. 참고 문서 전송
            if context_chunks:
                refs = [
                    {
                        "doc_id": c["doc_id"],
                        "file_name": c["file_name"],
                        "page": c.get("page_number"),
                        "score": round(c["score"], 3),
                    }
                    for c in context_chunks
                ]
                yield f"data: {json.dumps({'type': 'references', 'refs': refs})}\n\n"

            # 6. DB 저장
            with get_session() as db_session:
                # 사용자 메시지 저장
                user_msg = ChatMessage(
                    session_id=session_id,
                    user_id=user.user_id,
                    sender_type="user",
                    message=req.message,
                )
                db_session.add(user_msg)
                db_session.flush()

                # 어시스턴트 메시지 저장
                assistant_msg = ChatMessage(
                    session_id=session_id,
                    sender_type="assistant",
                    message=full_response,
                )
                db_session.add(assistant_msg)
                db_session.flush()

                # 참고 문서 저장
                for chunk in context_chunks:
                    db_session.add(MsgRef(
                        msg_id=assistant_msg.msg_id,
                        doc_id=chunk["doc_id"],
                        chunk_id=chunk["chunk_id"],
                        relevance_score=chunk["score"],
                    ))

                # 세션 제목 자동 설정 (첫 메시지 기반)
                chat_session_update = db_session.query(ChatSession).filter(
                    ChatSession.session_id == session_id
                ).first()
                if chat_session_update and not chat_session_update.title:
                    chat_session_update.title = req.message[:50]
                if chat_session_update:
                    chat_session_update.updated_at = datetime.now(timezone.utc)

                # Audit log
                db_session.add(AuditLog(
                    user_id=user.user_id,
                    action_type="chat_query",
                    target_type="chat_session",
                    target_id=session_id,
                    description=req.message[:200],
                ))

            yield f"data: {json.dumps({'type': 'done', 'msg_id': assistant_msg.msg_id})}\n\n"

        except Exception as e:
            logger.error("Stream chat error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

**Step 4: `app/api/main.py` 에 chat 라우터 등록**

```python
from app.api.routes import documents, processing, health, images, auth, chat

# ... 기존 코드 ...
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
```

**Step 5: Commit**

```bash
git add app/chat/ app/api/routes/chat.py app/api/main.py
git commit -m "feat: add RAG-LLM streaming chat API with RBAC"
```

---

### Task 7: 웹 검색 프록시 API

**Files:**
- Create: `app/api/routes/search.py`
- Modify: `app/api/main.py`
- Modify: `app/config.py`

**Step 1: `app/config.py` 에 웹 검색 설정 추가**

```python
    # Web Search
    searxng_url: str = "http://searxng:8080"
    web_search_enabled: bool = True
    web_search_deny_patterns: list[str] = []  # 차단할 키워드 패턴
```

**Step 2: `app/api/routes/search.py` 생성**

```python
import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db.models import AuditLog, User, WebSearchLog
from app.db.postgres import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

# 차단할 기본 패턴 (사내 민감 정보 예시)
DEFAULT_DENY_PATTERNS = [
    r"\b\d{3}-\d{4}-\d{4}\b",  # 전화번호
    r"\b[A-Z]{2,}-\d{3,}\b",   # 내부 프로젝트 코드 패턴
]


class WebSearchRequest(BaseModel):
    query: str
    session_id: int | None = None
    max_results: int = 5


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    results: list[WebSearchResult]
    query: str
    blocked: bool = False
    block_reason: str | None = None


def is_query_blocked(query: str) -> tuple[bool, str | None]:
    patterns = DEFAULT_DENY_PATTERNS + (settings.web_search_deny_patterns or [])
    for pattern in patterns:
        if re.search(pattern, query):
            return True, f"Query contains restricted pattern: {pattern}"
    return False, None


@router.post("/web", response_model=WebSearchResponse)
def web_search(
    req: WebSearchRequest,
    user: User = Depends(get_current_user),
):
    if not settings.web_search_enabled:
        raise HTTPException(status_code=503, detail="Web search is disabled")

    blocked, block_reason = is_query_blocked(req.query)

    # 항상 로그 기록
    with get_session() as session:
        session.add(WebSearchLog(
            user_id=user.user_id,
            session_id=req.session_id,
            query=req.query,
            was_blocked=blocked,
            block_reason=block_reason,
        ))
        session.add(AuditLog(
            user_id=user.user_id,
            action_type="web_search",
            description=f"query={req.query[:100]}",
        ))

    if blocked:
        return WebSearchResponse(query=req.query, results=[], blocked=True, block_reason=block_reason)

    # SearXNG 호출
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{settings.searxng_url}/search",
                params={
                    "q": req.query,
                    "format": "json",
                    "language": "ko",
                    "categories": "general",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as e:
        logger.error("SearXNG error: %s", e)
        raise HTTPException(status_code=503, detail="Search service unavailable")

    results = [
        WebSearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content", "")[:300],
        )
        for r in data.get("results", [])[:req.max_results]
    ]

    # 결과 수 업데이트
    with get_session() as session:
        log = session.query(WebSearchLog).filter(
            WebSearchLog.user_id == user.user_id,
            WebSearchLog.query == req.query,
        ).order_by(WebSearchLog.created_at.desc()).first()
        if log:
            log.results_count = len(results)

    return WebSearchResponse(query=req.query, results=results)
```

**Step 3: `app/api/main.py` 에 search 라우터 등록**

```python
from app.api.routes import documents, processing, health, images, auth, chat, search

app.include_router(search.router, prefix="/api/v1/search", tags=["Search"])
```

**Step 4: Commit**

```bash
git add app/api/routes/search.py app/api/main.py app/config.py
git commit -m "feat: add web search proxy with audit logging and deny-list"
```

---

## Phase 3: Admin API

### Task 8: Admin API 라우터

**Files:**
- Create: `app/api/routes/admin.py`
- Modify: `app/api/main.py`

**Step 1: `app/api/routes/admin.py` 생성**

```python
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, require_admin
from app.auth.password import hash_password
from app.db.models import (
    AuditLog, Department, Document, LLMConfig, Role, SystemHealth, User,
)
from app.db.postgres import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


# === 사용자 관리 ===

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
def list_users(
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin),
):
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
        existing = session.query(User).filter(User.email == req.email).first()
        if existing:
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

        session.add(AuditLog(
            user_id=admin.user_id,
            action_type="create_user",
            target_type="user",
            target_id=new_user.user_id,
        ))

        return UserListItem(
            user_id=new_user.user_id,
            usr_name=new_user.usr_name,
            email=new_user.email,
            role_name=role.role_name if role else "",
            dept_name=dept.name if dept else "",
            is_active=new_user.is_active,
            last_login=None,
            created_at=new_user.created_at.isoformat(),
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

        session.add(AuditLog(
            user_id=admin.user_id,
            action_type="update_user",
            target_type="user",
            target_id=user_id,
        ))

        role = session.query(Role).filter(Role.role_id == user.role_id).first()
        dept = session.query(Department).filter(Department.dept_id == user.dept_id).first()

        return UserListItem(
            user_id=user.user_id,
            usr_name=user.usr_name,
            email=user.email,
            role_name=role.role_name if role else "",
            dept_name=dept.name if dept else "",
            is_active=user.is_active,
            last_login=user.last_login.isoformat() if user.last_login else None,
            created_at=user.created_at.isoformat(),
        )


# === 문서 관리 ===

class DocStats(BaseModel):
    total: int
    indexed: int
    failed: int
    pending: int


@router.get("/documents/stats", response_model=DocStats)
def doc_stats(admin: User = Depends(require_admin)):
    with get_session() as session:
        total = session.query(Document).count()
        indexed = session.query(Document).filter(Document.status == "indexed").count()
        failed = session.query(Document).filter(Document.status == "failed").count()
        pending = session.query(Document).filter(Document.status == "pending").count()
        return DocStats(total=total, indexed=indexed, failed=failed, pending=pending)


# === 감사 로그 ===

class AuditLogItem(BaseModel):
    log_id: int
    user_id: int | None
    action_type: str
    target_type: str | None
    description: str | None
    ip_address: str | None
    created_at: str


@router.get("/audit-logs", response_model=list[AuditLogItem])
def list_audit_logs(
    limit: int = 100,
    offset: int = 0,
    action_type: str | None = None,
    admin: User = Depends(require_admin),
):
    with get_session() as session:
        q = session.query(AuditLog).order_by(AuditLog.created_at.desc())
        if action_type:
            q = q.filter(AuditLog.action_type == action_type)
        logs = q.offset(offset).limit(limit).all()
        return [
            AuditLogItem(
                log_id=l.log_id,
                user_id=l.user_id,
                action_type=l.action_type,
                target_type=l.target_type,
                description=l.description,
                ip_address=l.ip_address,
                created_at=l.created_at.isoformat(),
            )
            for l in logs
        ]


# === LLM 설정 ===

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
            model_name=config.model_name,
            vllm_url=config.vllm_url,
            system_prompt=config.system_prompt,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            context_chunks=config.context_chunks,
            is_active=config.is_active,
        )


@router.patch("/llm-config/{config_id}", response_model=LLMConfigResponse)
def update_llm_config(
    config_id: int,
    req: UpdateLLMConfigRequest,
    admin: User = Depends(require_admin),
):
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
            model_name=config.model_name,
            vllm_url=config.vllm_url,
            system_prompt=config.system_prompt,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            context_chunks=config.context_chunks,
            is_active=config.is_active,
        )
```

**Step 2: `app/api/main.py` 에 admin 라우터 등록**

```python
from app.api.routes import documents, processing, health, images, auth, chat, search, admin

app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
```

**Step 3: Commit**

```bash
git add app/api/routes/admin.py app/api/main.py
git commit -m "feat: add admin API (users, docs, audit logs, LLM config)"
```

---

## Phase 4: Next.js 프론트엔드

### Task 9: Next.js 프로젝트 초기화

**Files:**
- Create: `frontend/` 디렉토리 전체

**Step 1: Next.js 프로젝트 생성**

```bash
cd /Users/sae/Desktop/llm_again
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*"
```

**Step 2: 필요 패키지 설치**

```bash
cd /Users/sae/Desktop/llm_again/frontend
npm install zustand @tanstack/react-query axios react-markdown
npm install remark-gfm rehype-highlight highlight.js
npm install lucide-react
npm install -D @types/node
```

**Step 3: `frontend/lib/api.ts` 생성 — API 클라이언트**

```typescript
import axios from "axios";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

// 요청마다 JWT 자동 첨부
api.interceptors.request.use((config) => {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// 401 시 자동 갱신
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      const refreshToken = localStorage.getItem("refresh_token");
      if (refreshToken) {
        try {
          const res = await axios.post(
            `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/refresh`,
            { refresh_token: refreshToken }
          );
          localStorage.setItem("access_token", res.data.access_token);
          err.config.headers.Authorization = `Bearer ${res.data.access_token}`;
          return api(err.config);
        } catch {
          localStorage.clear();
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(err);
  }
);
```

**Step 4: `frontend/lib/auth.ts` 생성 — 인증 상태 관리 (Zustand)**

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "./api";

interface AuthUser {
  user_id: number;
  usr_name: string;
  email: string;
  role_name: string;
  auth_level: number;
  dept_name: string;
}

interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isLoading: false,

      login: async (email, password) => {
        set({ isLoading: true });
        try {
          const res = await api.post("/api/v1/auth/login", { email, password });
          localStorage.setItem("access_token", res.data.access_token);
          localStorage.setItem("refresh_token", res.data.refresh_token);
          set({
            user: {
              user_id: res.data.user_id,
              usr_name: res.data.usr_name,
              email: res.data.email,
              role_name: res.data.role_name,
              auth_level: res.data.auth_level,
              dept_name: res.data.dept_name,
            },
          });
        } finally {
          set({ isLoading: false });
        }
      },

      logout: async () => {
        const refreshToken = localStorage.getItem("refresh_token");
        if (refreshToken) {
          await api.post("/api/v1/auth/logout", { refresh_token: refreshToken }).catch(() => {});
        }
        localStorage.clear();
        set({ user: null });
      },

      fetchMe: async () => {
        const token = localStorage.getItem("access_token");
        if (!token) return;
        try {
          const res = await api.get("/api/v1/auth/me");
          set({ user: res.data });
        } catch {
          set({ user: null });
        }
      },
    }),
    { name: "auth-store", partialize: (s) => ({ user: s.user }) }
  )
);
```

**Step 5: Commit**

```bash
cd /Users/sae/Desktop/llm_again
git add frontend/
git commit -m "feat: initialize Next.js frontend with auth client"
```

---

### Task 10: 로그인 페이지

**Files:**
- Create: `frontend/app/login/page.tsx`
- Modify: `frontend/app/layout.tsx`

**Step 1: `frontend/app/login/page.tsx` 생성**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { login, isLoading } = useAuthStore();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await login(email, password);
      router.push("/chat");
    } catch (err: any) {
      setError(err.response?.data?.detail || "로그인 실패");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white p-8 rounded-2xl shadow-md w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">사내 AI 어시스턴트</h1>
          <p className="text-sm text-gray-500 mt-1">로그인하여 시작하세요</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              이메일
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="이메일 주소"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              비밀번호
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="비밀번호"
              required
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {isLoading ? "로그인 중..." : "로그인"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

**Step 2: `frontend/app/layout.tsx` 수정 — 기본 레이아웃**

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "사내 AI 어시스턴트",
  description: "사내 문서 기반 AI Q&A 시스템",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/app/login/ frontend/app/layout.tsx
git commit -m "feat: add login page"
```

---

### Task 11: 채팅 레이아웃 + 사이드바

**Files:**
- Create: `frontend/app/chat/layout.tsx`
- Create: `frontend/app/chat/page.tsx`
- Create: `frontend/components/Sidebar.tsx`

**Step 1: `frontend/components/Sidebar.tsx` 생성**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { Plus, MessageSquare, Trash2, LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";

interface Session {
  session_id: number;
  title: string | null;
  created_at: string;
}

export default function Sidebar() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const router = useRouter();
  const params = useParams();
  const { user, logout } = useAuthStore();
  const currentSessionId = params?.sessionId ? Number(params.sessionId) : null;

  useEffect(() => {
    api.get("/api/v1/chat/sessions").then((r) => setSessions(r.data));
  }, []);

  const createSession = async () => {
    const res = await api.post("/api/v1/chat/sessions", {});
    setSessions((prev) => [res.data, ...prev]);
    router.push(`/chat/${res.data.session_id}`);
  };

  const deleteSession = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    await api.delete(`/api/v1/chat/sessions/${id}`);
    setSessions((prev) => prev.filter((s) => s.session_id !== id));
    if (currentSessionId === id) router.push("/chat");
  };

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <div className="w-64 h-screen bg-gray-900 text-white flex flex-col">
      {/* 헤더 */}
      <div className="p-4 border-b border-gray-700">
        <h1 className="font-semibold text-sm text-gray-300">사내 AI 어시스턴트</h1>
        <p className="text-xs text-gray-500 mt-0.5">{user?.dept_name}</p>
      </div>

      {/* 새 대화 버튼 */}
      <div className="p-3">
        <button
          onClick={createSession}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-700 text-sm transition-colors border border-gray-700"
        >
          <Plus size={16} />
          새 대화
        </button>
      </div>

      {/* 대화 목록 */}
      <div className="flex-1 overflow-y-auto px-2">
        {sessions.map((s) => (
          <div
            key={s.session_id}
            onClick={() => router.push(`/chat/${s.session_id}`)}
            className={`group flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer mb-0.5 text-sm transition-colors ${
              currentSessionId === s.session_id
                ? "bg-gray-700"
                : "hover:bg-gray-800"
            }`}
          >
            <div className="flex items-center gap-2 min-w-0">
              <MessageSquare size={14} className="shrink-0 text-gray-400" />
              <span className="truncate text-gray-300">
                {s.title || "새 대화"}
              </span>
            </div>
            <button
              onClick={(e) => deleteSession(s.session_id, e)}
              className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-opacity"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>

      {/* 사용자 정보 */}
      <div className="p-3 border-t border-gray-700">
        <div className="flex items-center justify-between">
          <div className="text-xs text-gray-400 truncate">
            <p className="font-medium text-gray-300">{user?.usr_name}</p>
            <p>{user?.role_name}</p>
          </div>
          <button
            onClick={handleLogout}
            className="text-gray-500 hover:text-gray-300 transition-colors"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: `frontend/app/chat/layout.tsx` 생성**

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { useAuthStore } from "@/lib/auth";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { user, fetchMe } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    fetchMe().then(() => {
      if (!useAuthStore.getState().user) {
        router.push("/login");
      }
    });
  }, []);

  if (!user) return null;

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
```

**Step 3: `frontend/app/chat/page.tsx` 생성**

```tsx
export default function ChatIndexPage() {
  return (
    <div className="h-full flex items-center justify-center bg-gray-50">
      <div className="text-center text-gray-400">
        <p className="text-lg">왼쪽에서 새 대화를 시작하거나</p>
        <p className="text-lg">기존 대화를 선택하세요</p>
      </div>
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add frontend/app/chat/ frontend/components/
git commit -m "feat: add chat layout with sidebar"
```

---

### Task 12: 채팅 UI — 스트리밍 메시지

**Files:**
- Create: `frontend/app/chat/[sessionId]/page.tsx`
- Create: `frontend/components/ChatMessage.tsx`
- Create: `frontend/components/ChatInput.tsx`

**Step 1: `frontend/components/ChatMessage.tsx` 생성**

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText } from "lucide-react";

interface Reference {
  doc_id: number;
  file_name: string;
  page: number | null;
  score: number;
}

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  references?: Reference[];
  isStreaming?: boolean;
}

export default function ChatMessage({
  role,
  content,
  references,
  isStreaming,
}: ChatMessageProps) {
  return (
    <div className={`flex gap-3 py-4 ${role === "user" ? "justify-end" : "justify-start"}`}>
      {role === "assistant" && (
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
          AI
        </div>
      )}

      <div className={`max-w-[75%] ${role === "user" ? "order-first" : ""}`}>
        {/* 메시지 버블 */}
        <div
          className={`px-4 py-3 rounded-2xl text-sm ${
            role === "user"
              ? "bg-blue-600 text-white ml-auto"
              : "bg-white border border-gray-200 text-gray-800"
          }`}
        >
          {role === "assistant" ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm max-w-none">
              {content}
            </ReactMarkdown>
          ) : (
            <p className="whitespace-pre-wrap">{content}</p>
          )}
          {isStreaming && (
            <span className="inline-block w-1.5 h-4 bg-gray-400 animate-pulse ml-1" />
          )}
        </div>

        {/* 참고 문서 */}
        {references && references.length > 0 && (
          <div className="mt-2 space-y-1">
            {references.map((ref, i) => (
              <div
                key={i}
                className="flex items-center gap-2 text-xs text-gray-500 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-100"
              >
                <FileText size={12} />
                <span className="truncate">{ref.file_name}</span>
                {ref.page && <span className="text-gray-400">p.{ref.page}</span>}
                <span className="ml-auto text-gray-300">{(ref.score * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {role === "user" && (
        <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-gray-600 text-xs font-bold shrink-0">
          나
        </div>
      )}
    </div>
  );
}
```

**Step 2: `frontend/components/ChatInput.tsx` 생성**

```tsx
"use client";

import { useState, useRef } from "react";
import { Send, Globe } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string, options: { searchScope: string; useWebSearch: boolean }) => void;
  isStreaming: boolean;
}

export default function ChatInput({ onSend, isStreaming }: ChatInputProps) {
  const [message, setMessage] = useState("");
  const [searchScope, setSearchScope] = useState("all");
  const [useWebSearch, setUseWebSearch] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    if (!message.trim() || isStreaming) return;
    onSend(message.trim(), { searchScope, useWebSearch });
    setMessage("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  };

  return (
    <div className="border-t border-gray-200 bg-white p-4">
      {/* 옵션 바 */}
      <div className="flex items-center gap-3 mb-2 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <span>검색 범위:</span>
          <select
            value={searchScope}
            onChange={(e) => setSearchScope(e.target.value)}
            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs"
          >
            <option value="all">전체</option>
            <option value="dept">내 부서</option>
          </select>
        </div>
        <button
          onClick={() => setUseWebSearch(!useWebSearch)}
          className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-colors ${
            useWebSearch
              ? "border-blue-300 bg-blue-50 text-blue-600"
              : "border-gray-200 text-gray-400"
          }`}
        >
          <Globe size={11} />
          웹 검색
        </button>
      </div>

      {/* 입력창 */}
      <div className="flex items-end gap-2 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onInput={handleTextareaInput}
          onKeyDown={handleKeyDown}
          placeholder="메시지를 입력하세요... (Enter: 전송, Shift+Enter: 줄바꿈)"
          rows={1}
          className="flex-1 bg-transparent text-sm resize-none outline-none min-h-[24px] max-h-[200px]"
          disabled={isStreaming}
        />
        <button
          onClick={handleSend}
          disabled={!message.trim() || isStreaming}
          className="p-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
```

**Step 3: `frontend/app/chat/[sessionId]/page.tsx` 생성**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import ChatMessage from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";

interface Message {
  msg_id?: number;
  role: "user" | "assistant";
  content: string;
  references?: Array<{ doc_id: number; file_name: string; page: number | null; score: number }>;
  isStreaming?: boolean;
}

export default function ChatPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 기존 메시지 로드
  useEffect(() => {
    if (!sessionId) return;
    api.get(`/api/v1/chat/sessions/${sessionId}/messages`).then((res) => {
      setMessages(
        res.data.map((m: any) => ({
          msg_id: m.msg_id,
          role: m.sender_type,
          content: m.message,
        }))
      );
    });
  }, [sessionId]);

  // 새 메시지 올 때마다 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (
    text: string,
    options: { searchScope: string; useWebSearch: boolean }
  ) => {
    // 사용자 메시지 즉시 추가
    setMessages((prev) => [...prev, { role: "user", content: text }]);

    // 빈 어시스턴트 메시지 추가 (스트리밍용)
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", isStreaming: true },
    ]);
    setIsStreaming(true);

    const token = localStorage.getItem("access_token");
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/chat/sessions/${sessionId}/stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: text,
          search_scope: options.searchScope,
          use_web_search: options.useWebSearch,
        }),
      }
    );

    if (!response.body) return;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let currentRefs: Message["references"] = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const lines = decoder.decode(value).split("\n");
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(line.slice(6));

          if (data.type === "token") {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = {
                ...last,
                content: last.content + data.content,
              };
              return updated;
            });
          } else if (data.type === "references") {
            currentRefs = data.refs;
          } else if (data.type === "done") {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                isStreaming: false,
                references: currentRefs,
                msg_id: data.msg_id,
              };
              return updated;
            });
          }
        } catch {}
      }
    }

    setIsStreaming(false);
  };

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 max-w-4xl mx-auto w-full">
        {messages.map((msg, i) => (
          <ChatMessage
            key={i}
            role={msg.role}
            content={msg.content}
            references={msg.references}
            isStreaming={msg.isStreaming}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* 입력창 */}
      <div className="max-w-4xl mx-auto w-full">
        <ChatInput onSend={sendMessage} isStreaming={isStreaming} />
      </div>
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add frontend/app/chat/ frontend/components/ChatMessage.tsx frontend/components/ChatInput.tsx
git commit -m "feat: add streaming chat UI with reference display"
```

---

### Task 13: Docker Compose — 프론트엔드 서비스 추가

**Files:**
- Create: `frontend/Dockerfile`
- Modify: `docker-compose.yml`

**Step 1: `frontend/Dockerfile` 생성**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

**Step 2: `frontend/next.config.ts` 수정 — standalone 출력 활성화**

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

**Step 3: `docker-compose.yml` 에 frontend 서비스 추가**

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
    container_name: rag-frontend
    ports:
      - "3000:3000"
    depends_on:
      - api
    restart: unless-stopped
```

**Step 4: `.env.example` 에 추가**

```ini
# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Step 5: 전체 빌드 확인**

```bash
cd /Users/sae/Desktop/llm_again
docker compose build frontend
docker compose up frontend -d
curl http://localhost:3000
```

Expected: Next.js HTML 응답

**Step 6: Commit**

```bash
git add frontend/Dockerfile frontend/next.config.ts docker-compose.yml .env.example
git commit -m "feat: dockerize Next.js frontend"
```

---

## 최종 통합 확인

### Task 14: 전체 시스템 통합 테스트

**Step 1: 전체 서비스 시작 (vLLM 제외)**

```bash
cd /Users/sae/Desktop/llm_again
docker compose up -d postgres redis mineru-api api frontend
docker compose ps
```

**Step 2: API 헬스체크**

```bash
curl http://localhost:8000/health
curl http://localhost:8000/docs  # Swagger UI 확인
```

**Step 3: 로그인 테스트**

```bash
# 테스트 유저 생성
docker compose exec api python3 -c "
from app.auth.password import hash_password
from app.db.models import User
from app.db.postgres import get_session
with get_session() as s:
    u = User(pwd=hash_password('test1234'), usr_name='관리자', email='admin@company.com', dept_id=1, role_id=1)
    s.add(u)
print('done')
"

# 로그인
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.com","password":"test1234"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "Token: $TOKEN"
```

**Step 4: 채팅 세션 생성 테스트**

```bash
curl -X POST http://localhost:8000/api/v1/chat/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "테스트 대화"}'
```

**Step 5: 프론트엔드 브라우저 확인**

브라우저에서 `http://localhost:3000` 접속 → 로그인 → 채팅 확인

**Step 6: 최종 Commit**

```bash
git add .
git commit -m "feat: complete RAG-LLM service integration (auth + chat + admin + frontend)"
```

---

## 환경변수 전체 목록 (`.env` 필수 설정)

```ini
# DB (기존)
POSTGRES_HOST=postgres
POSTGRES_DB=rag_system
POSTGRES_USER=admin
POSTGRES_PASSWORD=your_secure_password

# JWT (신규 - 반드시 변경)
JWT_SECRET=your-very-secret-key-min-32-characters-long

# vLLM (신규)
VLLM_MODEL=Qwen/Qwen2.5-72B-Instruct-AWQ
VLLM_TENSOR_PARALLEL=1
VLLM_GPU_COUNT=1

# SearXNG (신규)
SEARXNG_SECRET=your-searxng-secret

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 참고: vLLM 모델 다운로드 (첫 실행)

```bash
# HuggingFace에서 Qwen2.5-72B-AWQ 사전 다운로드
pip install huggingface_hub
huggingface-cli download Qwen/Qwen2.5-72B-Instruct-AWQ \
  --local-dir /data/models/vllm/Qwen2.5-72B-Instruct-AWQ

# 또는 컨테이너 시작 시 자동 다운로드 (HF_TOKEN 필요)
docker compose up vllm-server
```
