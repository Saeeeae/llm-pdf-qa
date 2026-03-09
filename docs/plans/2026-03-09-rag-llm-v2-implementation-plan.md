# RAG-LLM v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the monolithic RAG-LLM system into 3 independent projects (rag-pipeline, rag-serving, rag-sync-monitor) in a monorepo with shared DB infrastructure, pgvector hybrid search, Neo4j GraphRAG, and BGE-M3 embeddings.

**Architecture:** Monorepo with `shared/` (SQL, ModelRegistry, config), 3 backend projects each with their own docker-compose, and a shared `docker-compose.base.yml` for PostgreSQL+pgvector, Neo4j, Redis. Each project imports from `shared/` via Python path. RBAC is department-based only. Existing Next.js frontend is preserved.

**Tech Stack:** FastAPI, PostgreSQL 16 + pgvector (HNSW), Neo4j 5, Redis 7, Celery, vLLM, BGE-M3 (1024-dim), BGE-reranker-v2-m3, MinerU (RAG-Anything), Streamlit, Next.js 14

---

## Phase 0: Project Restructure & Shared Infrastructure

### Task 0.1: Create Monorepo Directory Structure

**Files:**
- Create: `shared/`, `shared/sql/`, `shared/models/`, `shared/__init__.py`
- Create: `rag-pipeline/`, `rag-pipeline/pipeline/`, `rag-pipeline/tasks/`, `rag-pipeline/api/`, `rag-pipeline/scheduler/`
- Create: `rag-serving/`, `rag-serving/api/`, `rag-serving/api/routers/`, `rag-serving/api/rag/`, `rag-serving/admin/`, `rag-serving/vllm/`
- Create: `rag-sync-monitor/`, `rag-sync-monitor/sync/`, `rag-sync-monitor/trigger/`, `rag-sync-monitor/scheduler/`, `rag-sync-monitor/dashboard/`

**Step 1: Create all directories**

```bash
mkdir -p shared/{sql,models}
mkdir -p rag-pipeline/{pipeline,tasks,api,scheduler}
mkdir -p rag-serving/{api/{routers,rag},admin,vllm}
mkdir -p rag-sync-monitor/{sync,trigger,scheduler,dashboard}
```

**Step 2: Create __init__.py files**

```bash
touch shared/__init__.py shared/models/__init__.py
touch rag-pipeline/__init__.py rag-pipeline/pipeline/__init__.py rag-pipeline/tasks/__init__.py rag-pipeline/api/__init__.py
touch rag-serving/__init__.py rag-serving/api/__init__.py rag-serving/api/routers/__init__.py rag-serving/api/rag/__init__.py
touch rag-sync-monitor/__init__.py rag-sync-monitor/sync/__init__.py rag-sync-monitor/trigger/__init__.py
```

**Step 3: Commit**

```bash
git add shared/ rag-pipeline/ rag-serving/ rag-sync-monitor/
git commit -m "chore: create monorepo directory structure for v2"
```

---

### Task 0.2: Write SQL Init Script (shared/sql/init.sql)

**Files:**
- Create: `shared/sql/init.sql`

Take the user-provided SQL schema and add:
1. `CREATE EXTENSION IF NOT EXISTS vector;` (pgvector)
2. Modify `doc_chunk`: remove `qdrant_id`, add `embedding vector(1024)`, add `tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED`
3. Add HNSW index on `doc_chunk.embedding`
4. Add GIN index on `doc_chunk.tsv`
5. Add `graph_entities` table
6. Add `pipeline_logs` table
7. Add `sync_logs` table
8. Add `query_logs` table
9. Add `refresh_token` table
10. Add `llm_config` table
11. Add `web_search_log` table
12. Add `user_preference` table

**Step 1: Write init.sql**

```sql
-- =============================================================================
-- PostgreSQL Database Schema Initialization
-- On-Premise RAG-LLM System v2
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- =============================================================================
-- 1. Department
-- =============================================================================
CREATE TABLE IF NOT EXISTS department (
    dept_id SERIAL PRIMARY KEY,
    parent_dept_id INTEGER REFERENCES department(dept_id) ON DELETE SET NULL,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_department_parent ON department(parent_dept_id);

-- =============================================================================
-- 2. Roles (stored only, NOT used for access control)
-- =============================================================================
CREATE TABLE IF NOT EXISTS roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL UNIQUE,
    auth_level INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 3. Users
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    pwd TEXT NOT NULL,
    usr_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    dept_id INTEGER NOT NULL REFERENCES department(dept_id) ON DELETE RESTRICT,
    role_id INTEGER NOT NULL REFERENCES roles(role_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE,
    pwd_day INTEGER DEFAULT 90,
    failure INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_dept_id ON users(dept_id);
CREATE INDEX idx_users_role_id ON users(role_id);

-- =============================================================================
-- 4. Refresh Token (JWT)
-- =============================================================================
CREATE TABLE IF NOT EXISTS refresh_token (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45)
);
CREATE INDEX idx_refresh_token_user ON refresh_token(user_id);
CREATE INDEX idx_refresh_token_hash ON refresh_token(token_hash);

-- =============================================================================
-- 5. User Preference
-- =============================================================================
CREATE TABLE IF NOT EXISTS user_preference (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    preferences JSONB DEFAULT '{"search_scope": "all", "web_search": false, "theme": "light"}'
);

-- =============================================================================
-- 6. Doc Folder
-- =============================================================================
CREATE TABLE IF NOT EXISTS doc_folder (
    folder_id SERIAL PRIMARY KEY,
    parent_folder_id INTEGER REFERENCES doc_folder(folder_id) ON DELETE CASCADE,
    folder_name VARCHAR(255) NOT NULL,
    folder_path TEXT NOT NULL,
    dept_id INTEGER NOT NULL REFERENCES department(dept_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_doc_folder_parent ON doc_folder(parent_folder_id);
CREATE INDEX idx_doc_folder_dept ON doc_folder(dept_id);
CREATE INDEX idx_doc_folder_path ON doc_folder(folder_path);

-- =============================================================================
-- 7. Folder Access (department-based + exception grants)
-- =============================================================================
CREATE TABLE IF NOT EXISTS folder_access (
    access_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    folder_id INTEGER NOT NULL REFERENCES doc_folder(folder_id) ON DELETE CASCADE,
    is_recursive BOOLEAN DEFAULT FALSE,
    granted_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE UNIQUE INDEX idx_folder_access_user_folder ON folder_access(user_id, folder_id);
CREATE INDEX idx_folder_access_folder ON folder_access(folder_id);

-- =============================================================================
-- 8. Workspace (tables only, API deferred)
-- =============================================================================
CREATE TABLE IF NOT EXISTS workspace (
    ws_id SERIAL PRIMARY KEY,
    ws_name VARCHAR(200) NOT NULL,
    owner_dept_id INTEGER NOT NULL REFERENCES department(dept_id) ON DELETE RESTRICT,
    created_by INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_workspace_owner_dept ON workspace(owner_dept_id);
CREATE INDEX idx_workspace_created_by ON workspace(created_by);

-- =============================================================================
-- 9. Workspace Permission
-- =============================================================================
CREATE TABLE IF NOT EXISTS ws_permission (
    permission_id SERIAL PRIMARY KEY,
    ws_id INTEGER NOT NULL REFERENCES workspace(ws_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer'
);
CREATE UNIQUE INDEX idx_ws_permission_ws_user ON ws_permission(ws_id, user_id);

-- =============================================================================
-- 10. Workspace Invitation
-- =============================================================================
CREATE TABLE IF NOT EXISTS ws_invitation (
    invite_id SERIAL PRIMARY KEY,
    ws_id INTEGER NOT NULL REFERENCES workspace(ws_id) ON DELETE CASCADE,
    inviter_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    invitee_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX idx_ws_invitation_invitee ON ws_invitation(invitee_id, status);

-- =============================================================================
-- 11. Chat Session
-- =============================================================================
CREATE TABLE IF NOT EXISTS chat_session (
    session_id SERIAL PRIMARY KEY,
    ws_id INTEGER REFERENCES workspace(ws_id) ON DELETE SET NULL,
    created_by INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    title VARCHAR(300),
    session_type VARCHAR(20) NOT NULL DEFAULT 'private',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_chat_session_ws ON chat_session(ws_id);
CREATE INDEX idx_chat_session_created_by ON chat_session(created_by);

-- =============================================================================
-- 12. Session Participant
-- =============================================================================
CREATE TABLE IF NOT EXISTS session_participant (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX idx_session_participant_session_user ON session_participant(session_id, user_id);

-- =============================================================================
-- 13. Document
-- =============================================================================
CREATE TABLE IF NOT EXISTS document (
    doc_id SERIAL PRIMARY KEY,
    folder_id INTEGER REFERENCES doc_folder(folder_id) ON DELETE SET NULL,
    file_name VARCHAR(500) NOT NULL,
    path TEXT NOT NULL,
    type VARCHAR(50) NOT NULL,
    hash VARCHAR(64) UNIQUE NOT NULL,
    size BIGINT,
    dept_id INTEGER NOT NULL REFERENCES department(dept_id) ON DELETE RESTRICT,
    role_id INTEGER NOT NULL REFERENCES roles(role_id) ON DELETE RESTRICT,
    total_page_cnt INTEGER DEFAULT 0,
    language VARCHAR(10) DEFAULT 'ko',
    version INTEGER DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','processing','indexed','failed')),
    error_msg TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_document_folder ON document(folder_id, status);
CREATE INDEX idx_document_hash ON document(hash);
CREATE INDEX idx_document_dept ON document(dept_id);
CREATE INDEX idx_document_status ON document(status);
CREATE INDEX idx_document_created_at ON document(created_at DESC);

-- =============================================================================
-- 14. Doc Image
-- =============================================================================
CREATE TABLE IF NOT EXISTS doc_image (
    image_id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    page_number INTEGER,
    image_path TEXT NOT NULL,
    image_type VARCHAR(20),
    width INTEGER,
    height INTEGER,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_doc_image_doc ON doc_image(doc_id);

-- =============================================================================
-- 15. Doc Chunk (vector store with pgvector + tsvector)
-- =============================================================================
CREATE TABLE IF NOT EXISTS doc_chunk (
    chunk_id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    chunk_idx INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_cnt INTEGER DEFAULT 0,
    page_number INTEGER,
    embedding vector(1024),
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    embed_model VARCHAR(100) DEFAULT 'BAAI/bge-m3',
    chunk_type VARCHAR(20) DEFAULT 'text',
    image_id INTEGER REFERENCES doc_image(image_id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_doc_chunk_doc ON doc_chunk(doc_id, chunk_idx);

-- HNSW index for ANN vector search
CREATE INDEX idx_chunks_embedding ON doc_chunk
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index for full-text search
CREATE INDEX idx_chunks_tsv ON doc_chunk USING gin(tsv);

-- =============================================================================
-- 16. Graph Entities (Neo4j sync)
-- =============================================================================
CREATE TABLE IF NOT EXISTS graph_entities (
    id SERIAL PRIMARY KEY,
    doc_id INTEGER REFERENCES document(doc_id) ON DELETE CASCADE,
    entity_name TEXT NOT NULL,
    entity_type VARCHAR(50),
    neo4j_node_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_graph_entities_doc ON graph_entities(doc_id);
CREATE INDEX idx_graph_entities_name ON graph_entities(entity_name);

-- =============================================================================
-- 17. Chat Message
-- =============================================================================
CREATE TABLE IF NOT EXISTS chat_msg (
    msg_id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    sender_type VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_chat_msg_session ON chat_msg(session_id, created_at);

-- =============================================================================
-- 18. Message Reference (RAG source tracking)
-- =============================================================================
CREATE TABLE IF NOT EXISTS msg_ref (
    ref_id SERIAL PRIMARY KEY,
    msg_id INTEGER NOT NULL REFERENCES chat_msg(msg_id) ON DELETE CASCADE,
    doc_id INTEGER REFERENCES document(doc_id) ON DELETE SET NULL,
    chunk_id INTEGER REFERENCES doc_chunk(chunk_id) ON DELETE SET NULL,
    web_url VARCHAR(2048),
    relevance_score FLOAT
);
CREATE INDEX idx_msg_ref_msg ON msg_ref(msg_id);

-- =============================================================================
-- 19. Access Request
-- =============================================================================
CREATE TABLE IF NOT EXISTS access_request (
    req_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    target_ws_id INTEGER NOT NULL REFERENCES workspace(ws_id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    approve_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX idx_access_request_status ON access_request(status);

-- =============================================================================
-- 20. Audit Log
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    log_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    action_type VARCHAR(50) NOT NULL,
    target_type VARCHAR(50),
    target_id INTEGER,
    description TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_audit_log_user ON audit_log(user_id);
CREATE INDEX idx_audit_log_action ON audit_log(action_type);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at DESC);

-- =============================================================================
-- 21. LLM Config
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
-- 22. Web Search Log
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
CREATE INDEX idx_web_search_log_user ON web_search_log(user_id);

-- =============================================================================
-- 23. Pipeline Logs
-- =============================================================================
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id SERIAL PRIMARY KEY,
    doc_id INTEGER REFERENCES document(doc_id) ON DELETE CASCADE,
    stage VARCHAR(30) NOT NULL
        CHECK (stage IN ('mineru_parse','chunk','embed','graph_extract','index')),
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('running','success','failed')),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metadata JSONB
);
CREATE INDEX idx_pipeline_logs_doc ON pipeline_logs(doc_id);
CREATE INDEX idx_pipeline_logs_status ON pipeline_logs(status);

-- =============================================================================
-- 24. Sync Logs
-- =============================================================================
CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(20)
        CHECK (sync_type IN ('user','file','full','incremental')),
    source_ip VARCHAR(45),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    files_added INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    users_added INTEGER DEFAULT 0,
    status VARCHAR(20)
        CHECK (status IN ('running','success','failed')),
    error_message TEXT
);
CREATE INDEX idx_sync_logs_status ON sync_logs(status);

-- =============================================================================
-- 25. Query Logs
-- =============================================================================
CREATE TABLE IF NOT EXISTS query_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id),
    session_id INTEGER REFERENCES chat_session(session_id) ON DELETE SET NULL,
    prompt TEXT NOT NULL,
    retrieved_chunks JSONB,
    reranked_chunks JSONB,
    graph_context JSONB,
    final_answer TEXT,
    model_name VARCHAR(100),
    latency_ms INTEGER,
    token_count_in INTEGER,
    token_count_out INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_query_logs_user ON query_logs(user_id);
CREATE INDEX idx_query_logs_created ON query_logs(created_at DESC);

-- =============================================================================
-- 26. System Job
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_job (
    job_id SERIAL PRIMARY KEY,
    job_name VARCHAR(200) NOT NULL,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'idle',
    config_json JSONB,
    last_run_at TIMESTAMP WITH TIME ZONE,
    next_run_at TIMESTAMP WITH TIME ZONE,
    last_error TEXT
);
CREATE INDEX idx_system_job_type ON system_job(job_type);

-- =============================================================================
-- 27. System Health
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_health (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_time_ms FLOAT,
    metadata_json JSONB,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_system_health_service ON system_health(service_name);
CREATE INDEX idx_system_health_checked_at ON system_health(checked_at DESC);

-- =============================================================================
-- Triggers for updated_at
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_document_updated_at BEFORE UPDATE ON document
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_doc_chunk_updated_at BEFORE UPDATE ON doc_chunk
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_chat_session_updated_at BEFORE UPDATE ON chat_session
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Seed Data
-- =============================================================================
INSERT INTO department (name) VALUES ('Admin'), ('Research'), ('Clinical_Team'), ('QA')
    ON CONFLICT (name) DO NOTHING;

INSERT INTO roles (role_name, auth_level) VALUES
    ('Admin', 100), ('Manager', 50), ('Member', 10), ('Viewer', 1)
    ON CONFLICT (role_name) DO NOTHING;

INSERT INTO llm_config (model_name, vllm_url, is_active) VALUES
    ('qwen2.5-72b', 'http://vllm-server:8001/v1', TRUE);

-- =============================================================================
-- Views
-- =============================================================================
CREATE OR REPLACE VIEW user_activity_summary AS
SELECT
    u.user_id, u.usr_name, d.name AS department, r.role_name,
    COUNT(al.log_id) AS total_actions,
    COUNT(al.log_id) FILTER (WHERE al.action_type = 'query') AS total_queries,
    MAX(al.created_at) AS last_activity
FROM users u
JOIN department d ON u.dept_id = d.dept_id
JOIN roles r ON u.role_id = r.role_id
LEFT JOIN audit_log al ON u.user_id = al.user_id
GROUP BY u.user_id, u.usr_name, d.name, r.role_name;

CREATE OR REPLACE VIEW document_stats AS
SELECT
    doc.doc_id, doc.file_name, d.name AS department, r.role_name,
    df.folder_name, doc.status,
    COUNT(dc.chunk_id) AS chunk_count, doc.created_at
FROM document doc
JOIN department d ON doc.dept_id = d.dept_id
JOIN roles r ON doc.role_id = r.role_id
LEFT JOIN doc_folder df ON doc.folder_id = df.folder_id
LEFT JOIN doc_chunk dc ON doc.doc_id = dc.doc_id
GROUP BY doc.doc_id, doc.file_name, d.name, r.role_name, df.folder_name, doc.status, doc.created_at;

-- =============================================================================
-- Permissions
-- =============================================================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO admin;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO admin;
```

**Step 2: Commit**

```bash
git add shared/sql/init.sql
git commit -m "feat: add v2 SQL schema with pgvector, tsvector, pipeline/sync/query logs"
```

---

### Task 0.3: Shared Config (shared/config.py)

**Files:**
- Create: `shared/config.py`

**Step 1: Write shared config**

Refactor from existing `app/config.py`. Split into shared base settings used by all 3 projects.

```python
# shared/config.py
from pydantic_settings import BaseSettings
from typing import Optional


class SharedSettings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "rag_system"
    postgres_user: str = "admin"
    postgres_password: str = "changeme"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Neo4j
    neo4j_url: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Celery
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # Embedding
    embedding_model_name: str = "BAAI/bge-m3"
    embedding_model_dir: str = "/models/embedding"
    embedding_device: str = "cuda"
    embedding_batch_size: int = 32

    # Reranker
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    reranker_model_dir: str = "/models/reranker"
    reranker_device: str = "cuda"

    # JWT
    jwt_secret: str = "CHANGE_THIS_SECRET_IN_PRODUCTION_MIN_32_CHARS"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    # HuggingFace
    hf_token: Optional[str] = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


shared_settings = SharedSettings()
```

**Step 2: Commit**

```bash
git add shared/config.py
git commit -m "feat: add shared config with postgres, neo4j, redis, embedding settings"
```

---

### Task 0.4: Model Registry (shared/models/registry.py)

**Files:**
- Create: `shared/models/registry.py`

**Step 1: Write ModelRegistry**

```python
# shared/models/registry.py
import os
import logging
from dataclasses import dataclass, field
from sentence_transformers import SentenceTransformer, CrossEncoder

from shared.config import shared_settings

logger = logging.getLogger(__name__)


@dataclass
class ModelRegistry:
    _embedding: SentenceTransformer = field(default=None, init=False, repr=False)
    _reranker: CrossEncoder = field(default=None, init=False, repr=False)

    def embedding(self) -> SentenceTransformer:
        if self._embedding is None:
            model_dir = shared_settings.embedding_model_dir
            if os.path.isdir(model_dir) and os.listdir(model_dir):
                model_path = model_dir
            else:
                model_path = shared_settings.embedding_model_name
            logger.info("Loading embedding model: %s (device=%s)", model_path, shared_settings.embedding_device)
            self._embedding = SentenceTransformer(
                model_path,
                device=shared_settings.embedding_device,
                cache_folder=model_dir,
            )
        return self._embedding

    def reranker(self) -> CrossEncoder:
        if self._reranker is None:
            model_dir = shared_settings.reranker_model_dir
            if os.path.isdir(model_dir) and os.listdir(model_dir):
                model_path = model_dir
            else:
                model_path = shared_settings.reranker_model_name
            logger.info("Loading reranker model: %s (device=%s)", model_path, shared_settings.reranker_device)
            self._reranker = CrossEncoder(
                model_path,
                device=shared_settings.reranker_device,
                cache_folder=model_dir,
            )
        return self._reranker


registry = ModelRegistry()
```

**Step 2: Commit**

```bash
git add shared/models/registry.py shared/models/__init__.py
git commit -m "feat: add ModelRegistry with BGE-M3 embedding and BGE-reranker"
```

---

### Task 0.5: Shared DB Module (shared/db.py)

**Files:**
- Create: `shared/db.py`

**Step 1: Write shared DB session manager**

Adapt from existing `app/db/postgres.py` to be reusable.

```python
# shared/db.py
import logging
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from shared.config import shared_settings

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            shared_settings.postgres_dsn,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_session():
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Step 2: Commit**

```bash
git add shared/db.py
git commit -m "feat: add shared DB session manager"
```

---

### Task 0.6: Shared ORM Models (shared/models/orm.py)

**Files:**
- Create: `shared/models/orm.py`

**Step 1: Write ORM models**

Consolidate existing `app/db/models.py` + new tables (graph_entities, pipeline_logs, sync_logs, query_logs). Remove `qdrant_id` from DocChunk, keep `embedding vector(1024)`.

This is the existing models.py adapted:
- Add `GraphEntity`, `PipelineLog`, `SyncLog`, `QueryLog`
- DocChunk: remove qdrant_id (it doesn't exist in current ORM anyway - good)
- Keep all workspace/collaboration models

The full ORM file will be large. Key additions beyond existing `app/db/models.py`:

```python
# Add these to existing models

class GraphEntity(Base):
    __tablename__ = "graph_entities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("document.doc_id", ondelete="CASCADE"))
    entity_name = Column(Text, nullable=False)
    entity_type = Column(String(50))
    neo4j_node_id = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(Integer, ForeignKey("document.doc_id", ondelete="CASCADE"))
    stage = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    metadata_ = Column("metadata", JSON)


class SyncLog(Base):
    __tablename__ = "sync_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(String(20))
    source_ip = Column(String(45))
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True))
    files_added = Column(Integer, default=0)
    files_modified = Column(Integer, default=0)
    files_deleted = Column(Integer, default=0)
    users_added = Column(Integer, default=0)
    status = Column(String(20))
    error_message = Column(Text)


class QueryLog(Base):
    __tablename__ = "query_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    session_id = Column(Integer, ForeignKey("chat_session.session_id", ondelete="SET NULL"))
    prompt = Column(Text, nullable=False)
    retrieved_chunks = Column(JSON)
    reranked_chunks = Column(JSON)
    graph_context = Column(JSON)
    final_answer = Column(Text)
    model_name = Column(String(100))
    latency_ms = Column(Integer)
    token_count_in = Column(Integer)
    token_count_out = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

**Step 2: Copy existing models.py to shared/models/orm.py and add new models**

**Step 3: Commit**

```bash
git add shared/models/orm.py
git commit -m "feat: add shared ORM models with new tables for v2"
```

---

### Task 0.7: Docker Compose Base (docker-compose.base.yml)

**Files:**
- Create: `docker-compose.base.yml`

**Step 1: Write base compose with postgres+pgvector, neo4j, redis**

```yaml
# docker-compose.base.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: rag-postgres
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-rag_system}
      POSTGRES_USER: ${POSTGRES_USER:-admin}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
    ports:
      - "5432:5432"
    volumes:
      - ${POSTGRES_DATA_DIR:-./data/postgres}:/var/lib/postgresql/data
      - ./shared/sql/init.sql:/docker-entrypoint-initdb.d/01_init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-admin}"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  neo4j:
    image: neo4j:5
    container_name: rag-neo4j
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-changeme}
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - ${NEO4J_DATA_DIR:-./data/neo4j}:/data
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "${NEO4J_PASSWORD:-changeme}", "RETURN 1"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: rag-redis
    ports:
      - "6379:6379"
    volumes:
      - ${REDIS_DATA_DIR:-./data/redis}:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 3
    restart: unless-stopped

networks:
  default:
    name: rag-network

volumes:
  postgres-data:
  neo4j-data:
  redis-data:
```

**Step 2: Commit**

```bash
git add docker-compose.base.yml
git commit -m "feat: add base docker-compose with postgres+pgvector, neo4j, redis"
```

---

### Task 0.8: Environment Files

**Files:**
- Create: `.env.example` (update existing)
- Create: `rag-pipeline/.env.example`
- Create: `rag-serving/.env.example`
- Create: `rag-sync-monitor/.env.example`

**Step 1: Write env examples for each project**

**Step 2: Commit**

```bash
git add .env.example rag-pipeline/.env.example rag-serving/.env.example rag-sync-monitor/.env.example
git commit -m "feat: add .env.example files for all projects"
```

---

## Phase 1: rag-pipeline

### Task 1.1: Pipeline Config (rag-pipeline/config.py)

**Files:**
- Create: `rag-pipeline/config.py`

```python
# rag-pipeline/config.py
from shared.config import SharedSettings


class PipelineSettings(SharedSettings):
    # MinerU
    mineru_api_url: str = "http://mineru-api:9000"
    mineru_backend: str = "hybrid-auto-engine"
    mineru_lang: str = "korean"

    # Scanning
    source_scan_paths: str = "/mnt/nas/documents"

    # Chunking
    chunk_strategy: str = "hybrid"
    chunk_size: int = 512
    chunk_overlap: int = 50
    chunk_min_section_tokens: int = 80

    # Image
    enable_image_embedding: bool = True
    image_store_dir: str = "/data/images"

    # API
    pipeline_api_port: int = 8001

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


pipeline_settings = PipelineSettings()
```

**Step 2: Commit**

---

### Task 1.2: Scanner (rag-pipeline/pipeline/scanner.py)

**Files:**
- Create: `rag-pipeline/pipeline/scanner.py`

Adapt from existing `app/pipeline/scanner.py`. Key changes:
- Use SHA-256 hash (already does)
- Compare against `document` table via shared DB
- Return added/modified/deleted file lists
- Update `document.status` for modified files

```python
# rag-pipeline/pipeline/scanner.py
import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from shared.db import get_session
from shared.models.orm import Document

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls", ".pptx",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff",
}


@dataclass
class ScanDiff:
    added: list[dict] = field(default_factory=list)      # {path, name, ext, size, hash}
    modified: list[dict] = field(default_factory=list)    # {path, name, ext, size, hash, doc_id}
    deleted: list[int] = field(default_factory=list)      # doc_ids


def compute_file_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def scan_directory(directory: str, recursive: bool = True) -> list[dict]:
    """Scan directory and return file metadata."""
    files = []
    base = Path(directory)
    if not base.is_dir():
        logger.warning("Directory not found: %s", directory)
        return files

    walker = os.walk(directory) if recursive else [(directory, [], os.listdir(directory))]
    for root, _, filenames in walker:
        for fname in filenames:
            fpath = Path(root) / fname
            if not fpath.is_file():
                continue
            ext = fpath.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            files.append({
                "path": str(fpath),
                "name": fpath.name,
                "ext": ext.lstrip("."),
                "size": fpath.stat().st_size,
                "hash": compute_file_hash(str(fpath)),
            })
    return files


def diff_with_db(scanned_files: list[dict]) -> ScanDiff:
    """Compare scanned files against DB to find added/modified/deleted."""
    diff = ScanDiff()

    with get_session() as session:
        existing = session.query(Document).filter(Document.status != 'failed').all()
        db_by_path = {doc.path: doc for doc in existing}
        db_by_hash = {doc.hash: doc for doc in existing}

    scanned_paths = set()
    for f in scanned_files:
        scanned_paths.add(f["path"])
        if f["path"] in db_by_path:
            doc = db_by_path[f["path"]]
            if doc.hash != f["hash"]:
                diff.modified.append({**f, "doc_id": doc.doc_id})
        elif f["hash"] not in db_by_hash:
            diff.added.append(f)

    for path, doc in db_by_path.items():
        if path not in scanned_paths:
            diff.deleted.append(doc.doc_id)

    logger.info("Scan diff: +%d ~%d -%d", len(diff.added), len(diff.modified), len(diff.deleted))
    return diff
```

**Step 2: Commit**

---

### Task 1.3: Parser (rag-pipeline/pipeline/parser.py)

**Files:**
- Create: `rag-pipeline/pipeline/parser.py`

Adapter that calls MinerU API (existing pattern from `app/mineru_api.py` + `app/parsers/`).

**Step 1: Write parser that delegates to MinerU API or local parsers**

Reuse existing parser logic from `app/parsers/` and `app/mineru_api.py`.

**Step 2: Commit**

---

### Task 1.4: Chunker (rag-pipeline/pipeline/chunker.py)

**Files:**
- Create: `rag-pipeline/pipeline/chunker.py`

**Step 1: Copy and adapt from `app/processing/chunker.py`**

Change import from `app.config` to `rag-pipeline/config.py`. Otherwise identical.

**Step 2: Commit**

---

### Task 1.5: Embedder (rag-pipeline/pipeline/embedder.py)

**Files:**
- Create: `rag-pipeline/pipeline/embedder.py`

**Step 1: Write embedder using shared ModelRegistry**

```python
# rag-pipeline/pipeline/embedder.py
import logging
import numpy as np
from shared.models.registry import registry

logger = logging.getLogger(__name__)


def embed_chunks(texts: list[str]) -> np.ndarray:
    """Embed document chunks using BGE-M3. Returns (N, 1024) normalized."""
    model = registry.embedding()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    )
    return embeddings


def embed_query(query: str) -> np.ndarray:
    """Embed a search query. Returns (1024,) normalized."""
    model = registry.embedding()
    return model.encode([query], normalize_embeddings=True)[0]
```

Note: BGE-M3 does NOT need `passage:` / `query:` prefixes (unlike E5).

**Step 2: Commit**

---

### Task 1.6: Indexer (rag-pipeline/pipeline/indexer.py)

**Files:**
- Create: `rag-pipeline/pipeline/indexer.py`

**Step 1: Write pgvector indexer**

```python
# rag-pipeline/pipeline/indexer.py
import logging
from shared.db import get_session
from shared.models.orm import DocChunk

logger = logging.getLogger(__name__)


def index_chunks(
    doc_id: int,
    chunks: list[dict],
    embeddings,
    embed_model: str = "BAAI/bge-m3",
) -> int:
    """Delete existing chunks for doc_id, insert new ones with embeddings.

    Args:
        chunks: list of {"text": str, "token_cnt": int, "chunk_idx": int, "page_number": int|None}
        embeddings: numpy array (N, 1024)

    Returns: number of chunks inserted
    """
    with get_session() as session:
        # Delete old chunks
        session.query(DocChunk).filter(DocChunk.doc_id == doc_id).delete()

        # Insert new
        records = []
        for chunk, emb in zip(chunks, embeddings):
            records.append(DocChunk(
                doc_id=doc_id,
                chunk_idx=chunk["chunk_idx"],
                content=chunk["text"],
                token_cnt=chunk["token_cnt"],
                page_number=chunk.get("page_number"),
                embedding=emb.tolist(),
                embed_model=embed_model,
                chunk_type=chunk.get("chunk_type", "text"),
            ))
        session.add_all(records)

    logger.info("Indexed %d chunks for doc_id=%d", len(records), doc_id)
    return len(records)
```

**Step 2: Commit**

---

### Task 1.7: Graph Extractor (rag-pipeline/pipeline/graph_extractor.py)

**Files:**
- Create: `rag-pipeline/pipeline/graph_extractor.py`

**Step 1: Write NER + Neo4j entity storage**

Uses spaCy or simple regex NER to extract entities from chunks, stores in `graph_entities` table and Neo4j.

```python
# rag-pipeline/pipeline/graph_extractor.py
import logging
from neo4j import GraphDatabase
from shared.config import shared_settings
from shared.db import get_session
from shared.models.orm import GraphEntity

logger = logging.getLogger(__name__)


def get_neo4j_driver():
    return GraphDatabase.driver(
        shared_settings.neo4j_url,
        auth=(shared_settings.neo4j_user, shared_settings.neo4j_password),
    )


def extract_entities(text: str) -> list[dict]:
    """Simple NER extraction. Returns [{"name": str, "type": str}]."""
    # Phase 1: simple regex/keyword extraction
    # Phase 2: upgrade to spaCy or LLM-based NER
    entities = []
    # Placeholder - implement with spaCy ko_core_news_sm or LLM
    return entities


def store_entities(doc_id: int, entities: list[dict]):
    """Store entities in PostgreSQL + Neo4j."""
    if not entities:
        return

    # PostgreSQL
    with get_session() as session:
        session.query(GraphEntity).filter(GraphEntity.doc_id == doc_id).delete()
        for ent in entities:
            session.add(GraphEntity(
                doc_id=doc_id,
                entity_name=ent["name"],
                entity_type=ent["type"],
            ))

    # Neo4j
    try:
        driver = get_neo4j_driver()
        with driver.session() as neo_session:
            for ent in entities:
                result = neo_session.run(
                    "MERGE (e:Entity {name: $name}) "
                    "SET e.type = $type "
                    "RETURN elementId(e) AS node_id",
                    name=ent["name"], type=ent["type"],
                )
                record = result.single()
                if record:
                    ent["neo4j_node_id"] = record["node_id"]

            # Create APPEARS_IN relationships
            for ent in entities:
                neo_session.run(
                    "MATCH (e:Entity {name: $name}) "
                    "MERGE (d:Document {doc_id: $doc_id}) "
                    "MERGE (e)-[:APPEARS_IN]->(d)",
                    name=ent["name"], doc_id=doc_id,
                )

            # Create CO_OCCURS relationships between entities in same doc
            if len(entities) > 1:
                names = [e["name"] for e in entities]
                neo_session.run(
                    "UNWIND $names AS n1 "
                    "UNWIND $names AS n2 "
                    "WITH n1, n2 WHERE n1 < n2 "
                    "MATCH (a:Entity {name: n1}), (b:Entity {name: n2}) "
                    "MERGE (a)-[:CO_OCCURS]->(b)",
                    names=names,
                )
        driver.close()
    except Exception as e:
        logger.warning("Neo4j storage failed (non-fatal): %s", e)

    logger.info("Stored %d entities for doc_id=%d", len(entities), doc_id)
```

**Step 2: Commit**

---

### Task 1.8: Orchestrator (rag-pipeline/pipeline/orchestrator.py)

**Files:**
- Create: `rag-pipeline/pipeline/orchestrator.py`

**Step 1: Write pipeline orchestrator with stage logging**

```python
# rag-pipeline/pipeline/orchestrator.py
import logging
from datetime import datetime, timezone

from shared.db import get_session
from shared.models.orm import Document, PipelineLog

from rag-pipeline.pipeline.parser import parse_document
from rag-pipeline.pipeline.chunker import chunk_text
from rag-pipeline.pipeline.embedder import embed_chunks
from rag-pipeline.pipeline.indexer import index_chunks
from rag-pipeline.pipeline.graph_extractor import extract_entities, store_entities

logger = logging.getLogger(__name__)


def log_stage(doc_id: int, stage: str, status: str, error: str = None, metadata: dict = None):
    with get_session() as session:
        log = PipelineLog(
            doc_id=doc_id, stage=stage, status=status,
            error_message=error, metadata_=metadata,
        )
        if status in ("success", "failed"):
            log.finished_at = datetime.now(timezone.utc)
        session.add(log)


def process_document(doc_id: int):
    """Full pipeline for one document: parse -> chunk -> embed -> index -> graph."""

    with get_session() as session:
        doc = session.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found")
        doc.status = "processing"

    try:
        # 1. Parse
        log_stage(doc_id, "mineru_parse", "running")
        parse_result = parse_document(doc.path)
        log_stage(doc_id, "mineru_parse", "success",
                  metadata={"pages": parse_result.total_pages})

        # 2. Chunk
        log_stage(doc_id, "chunk", "running")
        chunks = chunk_text(parse_result.raw_text)
        log_stage(doc_id, "chunk", "success",
                  metadata={"count": len(chunks)})

        if not chunks:
            with get_session() as session:
                d = session.query(Document).filter(Document.doc_id == doc_id).first()
                d.status = "indexed"
                d.total_page_cnt = parse_result.total_pages
            return

        # 3. Embed
        log_stage(doc_id, "embed", "running")
        texts = [c["text"] for c in chunks]
        embeddings = embed_chunks(texts)
        log_stage(doc_id, "embed", "success")

        # 4. Index (pgvector)
        log_stage(doc_id, "index", "running")
        index_chunks(doc_id, chunks, embeddings)
        log_stage(doc_id, "index", "success")

        # 5. Graph extract
        log_stage(doc_id, "graph_extract", "running")
        all_text = " ".join(texts)
        entities = extract_entities(all_text)
        store_entities(doc_id, entities)
        log_stage(doc_id, "graph_extract", "success",
                  metadata={"entities": len(entities)})

        # Mark complete
        with get_session() as session:
            d = session.query(Document).filter(Document.doc_id == doc_id).first()
            d.status = "indexed"
            d.total_page_cnt = parse_result.total_pages

        logger.info("Pipeline complete for doc_id=%d", doc_id)

    except Exception as e:
        with get_session() as session:
            d = session.query(Document).filter(Document.doc_id == doc_id).first()
            if d:
                d.status = "failed"
                d.error_msg = str(e)[:1000]
        logger.error("Pipeline failed for doc_id=%d: %s", doc_id, e)
        raise
```

Note: The import paths use hyphens which won't work in Python. The actual implementation will use underscores for Python package names or sys.path manipulation. Plan should use `rag_pipeline` as Python package name.

**Step 2: Commit**

---

### Task 1.9: Celery Tasks (rag-pipeline/tasks/)

**Files:**
- Create: `rag-pipeline/tasks/celery_app.py`
- Create: `rag-pipeline/tasks/pipeline_tasks.py`

**Step 1: Write Celery app and pipeline tasks**

Adapt from existing `app/tasks/celery_app.py` and `app/tasks/ingest_tasks.py`.

```python
# rag-pipeline/tasks/celery_app.py
from celery import Celery
from shared.config import shared_settings

app = Celery("rag_pipeline")
app.conf.update(
    broker_url=shared_settings.celery_broker_url,
    result_backend=shared_settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    task_routes={
        "rag_pipeline.tasks.*": {"queue": "pipeline"},
    },
)
```

```python
# rag-pipeline/tasks/pipeline_tasks.py
from rag_pipeline.tasks.celery_app import app
from rag_pipeline.pipeline.orchestrator import process_document


@app.task(name="rag_pipeline.tasks.process_document", bind=True, max_retries=2)
def process_document_task(self, doc_id: int):
    try:
        process_document(doc_id)
    except Exception as exc:
        self.retry(exc=exc, countdown=30)


@app.task(name="rag_pipeline.tasks.process_batch")
def process_batch_task(doc_ids: list[int]):
    for doc_id in doc_ids:
        process_document_task.delay(doc_id)
```

**Step 2: Commit**

---

### Task 1.10: Pipeline API (rag-pipeline/api/main.py)

**Files:**
- Create: `rag-pipeline/api/main.py`

**Step 1: Write FastAPI app for pipeline triggers**

```python
# rag-pipeline/api/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.db import get_session
from shared.models.orm import Document, PipelineLog
from rag_pipeline.tasks.pipeline_tasks import process_document_task, process_batch_task

app = FastAPI(title="RAG Pipeline API", version="2.0")


class TriggerRequest(BaseModel):
    doc_ids: list[int]


class TriggerResponse(BaseModel):
    message: str
    doc_ids: list[int]


@app.post("/pipeline/trigger", response_model=TriggerResponse)
def trigger_pipeline(req: TriggerRequest):
    if not req.doc_ids:
        raise HTTPException(400, "No doc_ids provided")
    process_batch_task.delay(req.doc_ids)
    return TriggerResponse(message="Pipeline triggered", doc_ids=req.doc_ids)


@app.post("/pipeline/trigger/full", response_model=TriggerResponse)
def trigger_full_reprocess():
    with get_session() as session:
        docs = session.query(Document.doc_id).all()
        doc_ids = [d.doc_id for d in docs]
    if not doc_ids:
        raise HTTPException(404, "No documents found")
    process_batch_task.delay(doc_ids)
    return TriggerResponse(message="Full reprocess triggered", doc_ids=doc_ids)


@app.get("/pipeline/status/{doc_id}")
def pipeline_status(doc_id: int):
    with get_session() as session:
        doc = session.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(404, "Document not found")
        logs = session.query(PipelineLog).filter(
            PipelineLog.doc_id == doc_id
        ).order_by(PipelineLog.started_at.desc()).all()
        return {
            "doc_id": doc_id,
            "status": doc.status,
            "stages": [
                {
                    "stage": log.stage,
                    "status": log.status,
                    "started_at": log.started_at.isoformat() if log.started_at else None,
                    "finished_at": log.finished_at.isoformat() if log.finished_at else None,
                    "error": log.error_message,
                }
                for log in logs
            ],
        }


@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 2: Commit**

---

### Task 1.11: Pipeline Docker (rag-pipeline/Dockerfile, docker-compose.yml)

**Files:**
- Create: `rag-pipeline/Dockerfile`
- Create: `rag-pipeline/docker-compose.yml`
- Create: `rag-pipeline/requirements.txt`

**Step 1: Write Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ../shared /app/shared
COPY . /app/rag_pipeline

ENV PYTHONPATH=/app
CMD ["uvicorn", "rag_pipeline.api.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

**Step 2: Write docker-compose.yml**

```yaml
# rag-pipeline/docker-compose.yml
# Extends docker-compose.base.yml
services:
  pipeline-api:
    build:
      context: ..
      dockerfile: rag-pipeline/Dockerfile
    container_name: rag-pipeline-api
    ports:
      - "8001:8001"
    env_file: ../.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  pipeline-worker:
    build:
      context: ..
      dockerfile: rag-pipeline/Dockerfile
    container_name: rag-pipeline-worker
    command: celery -A rag_pipeline.tasks.celery_app worker --loglevel=info -Q pipeline --concurrency=2
    env_file: ../.env
    volumes:
      - ${DOC_WATCH_DIR:-/data/documents}:/data/documents:ro
      - ${EMBEDDING_MODEL_DIR:-/data/models/embedding}:/models/embedding:ro
      - ${IMAGE_STORE_DIR:-/data/images}:/data/images
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  mineru-api:
    build:
      context: ..
      dockerfile: Dockerfile.mineru
    container_name: rag-mineru-api
    env_file: ../.env
    ports:
      - "9000:9000"
    volumes:
      - ${DOC_WATCH_DIR:-/data/documents}:/data/documents:ro
      - ${MINERU_MODEL_DIR:-/data/models/mineru}:/root/.cache/mineru
      - ${IMAGE_STORE_DIR:-/data/images}:/data/images
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped
```

**Step 3: Commit**

---

## Phase 2: rag-serving

### Task 2.1: Serving Config (rag-serving/config.py)

**Files:**
- Create: `rag-serving/config.py`

```python
# rag-serving/config.py
from shared.config import SharedSettings


class ServingSettings(SharedSettings):
    # vLLM
    vllm_base_url: str = "http://vllm-server:8000/v1"
    vllm_model_name: str = "qwen2.5-72b"

    # Web Search
    web_search_enabled: bool = True
    google_api_key: str = ""
    google_cx: str = ""

    # Serving
    serving_api_port: int = 8002

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


serving_settings = ServingSettings()
```

---

### Task 2.2: Hybrid Retriever (rag-serving/api/rag/retriever.py)

**Files:**
- Create: `rag-serving/api/rag/retriever.py`

**Step 1: Write hybrid search with RRF**

```python
# rag-serving/api/rag/retriever.py
import logging
from sqlalchemy import text
from shared.db import get_session

logger = logging.getLogger(__name__)


def dense_search(query_vector: list[float], dept_id: int, accessible_folder_ids: list[int],
                 search_scope: str = "all", limit: int = 20) -> list[dict]:
    """pgvector cosine similarity search with department-based RBAC."""
    params = {"vec": query_vector, "lim": limit}
    conditions = ["dc.embedding IS NOT NULL", "d.status = 'indexed'"]

    if search_scope == "dept":
        conditions.append("d.dept_id = :dept_id")
        params["dept_id"] = dept_id
    elif search_scope == "folder" and accessible_folder_ids:
        conditions.append("d.folder_id = ANY(:folder_ids)")
        params["folder_ids"] = accessible_folder_ids
    else:
        # "all" — user can see own dept + folders with explicit access
        conditions.append(
            "(d.dept_id = :dept_id OR d.folder_id = ANY(:folder_ids))"
        )
        params["dept_id"] = dept_id
        params["folder_ids"] = accessible_folder_ids or []

    where = "WHERE " + " AND ".join(conditions)
    sql = text(f"""
        SELECT dc.chunk_id, dc.doc_id, dc.chunk_idx, dc.content,
               dc.chunk_type, dc.page_number,
               1 - (dc.embedding <=> :vec::vector) AS dense_score,
               d.file_name
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
        {where}
        ORDER BY dc.embedding <=> :vec::vector
        LIMIT :lim
    """)

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
    return [dict(r._mapping) for r in rows]


def sparse_search(query_text: str, dept_id: int, accessible_folder_ids: list[int],
                  search_scope: str = "all", limit: int = 20) -> list[dict]:
    """Full-text search using tsvector with department-based RBAC."""
    params = {"query": query_text, "lim": limit}
    conditions = ["dc.tsv @@ plainto_tsquery('simple', :query)", "d.status = 'indexed'"]

    if search_scope == "dept":
        conditions.append("d.dept_id = :dept_id")
        params["dept_id"] = dept_id
    elif search_scope == "folder" and accessible_folder_ids:
        conditions.append("d.folder_id = ANY(:folder_ids)")
        params["folder_ids"] = accessible_folder_ids
    else:
        conditions.append(
            "(d.dept_id = :dept_id OR d.folder_id = ANY(:folder_ids))"
        )
        params["dept_id"] = dept_id
        params["folder_ids"] = accessible_folder_ids or []

    where = "WHERE " + " AND ".join(conditions)
    sql = text(f"""
        SELECT dc.chunk_id, dc.doc_id, dc.chunk_idx, dc.content,
               dc.chunk_type, dc.page_number,
               ts_rank(dc.tsv, plainto_tsquery('simple', :query)) AS sparse_score,
               d.file_name
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
        {where}
        ORDER BY sparse_score DESC
        LIMIT :lim
    """)

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
    return [dict(r._mapping) for r in rows]


def reciprocal_rank_fusion(dense_results: list[dict], sparse_results: list[dict],
                           k: int = 60) -> list[dict]:
    """Merge dense + sparse results using RRF."""
    scores = {}
    chunk_data = {}

    for rank, row in enumerate(dense_results):
        cid = row["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        chunk_data[cid] = row

    for rank, row in enumerate(sparse_results):
        cid = row["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        if cid not in chunk_data:
            chunk_data[cid] = row

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return [
        {**chunk_data[cid], "rrf_score": scores[cid]}
        for cid in sorted_ids
    ]


def hybrid_search(query_text: str, query_vector: list[float],
                  dept_id: int, accessible_folder_ids: list[int],
                  search_scope: str = "all", dense_limit: int = 20,
                  sparse_limit: int = 20) -> list[dict]:
    """Full hybrid search: dense + sparse + RRF merge."""
    dense = dense_search(query_vector, dept_id, accessible_folder_ids, search_scope, dense_limit)
    sparse = sparse_search(query_text, dept_id, accessible_folder_ids, search_scope, sparse_limit)
    return reciprocal_rank_fusion(dense, sparse)
```

**Step 2: Commit**

---

### Task 2.3: Reranker (rag-serving/api/rag/reranker.py)

**Files:**
- Create: `rag-serving/api/rag/reranker.py`

```python
# rag-serving/api/rag/reranker.py
import logging
from shared.models.registry import registry

logger = logging.getLogger(__name__)


def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Rerank chunks using BGE-reranker-v2-m3."""
    if not chunks:
        return []

    model = registry.reranker()
    pairs = [(query, c["content"][:512]) for c in chunks]
    scores = model.predict(pairs)

    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = float(score)

    ranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
    return ranked[:top_k]
```

**Step 2: Commit**

---

### Task 2.4: Graph Retriever (rag-serving/api/rag/graph_retriever.py)

**Files:**
- Create: `rag-serving/api/rag/graph_retriever.py`

```python
# rag-serving/api/rag/graph_retriever.py
import logging
from neo4j import GraphDatabase
from shared.config import shared_settings

logger = logging.getLogger(__name__)


def get_graph_context(query: str, max_hops: int = 2) -> str:
    """Extract entities from query, find 2-hop neighbors in Neo4j."""
    # Simple keyword extraction (upgrade to NER later)
    keywords = [w.strip() for w in query.split() if len(w.strip()) > 1]
    if not keywords:
        return ""

    try:
        driver = GraphDatabase.driver(
            shared_settings.neo4j_url,
            auth=(shared_settings.neo4j_user, shared_settings.neo4j_password),
        )
        context_parts = []
        with driver.session() as session:
            for keyword in keywords[:5]:
                result = session.run(
                    "MATCH (e:Entity) WHERE e.name CONTAINS $kw "
                    "OPTIONAL MATCH (e)-[r*1..2]-(neighbor:Entity) "
                    "RETURN e.name AS entity, e.type AS type, "
                    "collect(DISTINCT neighbor.name)[..10] AS neighbors "
                    "LIMIT 5",
                    kw=keyword,
                )
                for record in result:
                    neighbors = record["neighbors"]
                    if neighbors:
                        context_parts.append(
                            f"{record['entity']} ({record['type']}): "
                            f"related to {', '.join(neighbors)}"
                        )
        driver.close()

        if context_parts:
            return "=== Graph Context ===\n" + "\n".join(context_parts) + "\n=== End Graph ==="
        return ""
    except Exception as e:
        logger.warning("Graph retrieval failed (non-fatal): %s", e)
        return ""
```

**Step 2: Commit**

---

### Task 2.5: Generator (rag-serving/api/rag/generator.py)

**Files:**
- Create: `rag-serving/api/rag/generator.py`

Adapt from existing `app/chat/rag_pipeline.py` (build_messages + stream_llm_response). Add graph_context to prompt.

```python
# rag-serving/api/rag/generator.py
import json
import logging
from typing import Generator

import httpx

logger = logging.getLogger(__name__)


def build_messages(
    system_prompt: str,
    context_chunks: list[dict],
    graph_context: str,
    chat_history: list[dict],
    user_message: str,
) -> list[dict]:
    parts = [system_prompt]

    if graph_context:
        parts.append(graph_context)

    if context_chunks:
        chunk_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            page = f" p.{chunk['page_number']}" if chunk.get("page_number") else ""
            chunk_parts.append(f"[문서 {i}: {chunk['file_name']}{page}]\n{chunk['content'][:500]}")
        parts.append("=== 관련 문서 ===\n" + "\n\n".join(chunk_parts) + "\n=== 문서 끝 ===")
        parts.append("위 문서를 참고하여 답변하세요. 문서에 없는 내용은 모른다고 알려주세요.")

    messages = [{"role": "system", "content": "\n\n".join(parts)}]
    for msg in chat_history[-20:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})
    return messages


def stream_response(messages: list[dict], vllm_url: str, model_name: str,
                    max_tokens: int = 4096, temperature: float = 0.7,
                    top_p: float = 0.9) -> Generator[str, None, None]:
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stream": True,
    }
    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", f"{vllm_url}/chat/completions", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        continue
```

**Step 2: Commit**

---

### Task 2.6: Auth Router (rag-serving/api/routers/auth.py)

**Files:**
- Create: `rag-serving/api/routers/auth.py`
- Create: `rag-serving/api/auth/` (jwt.py, password.py, dependencies.py)

**Step 1: Copy and adapt from existing `app/auth/` and `app/api/routes/auth.py`**

Change imports from `app.db.*` to `shared.*`. Logic remains the same.

**Step 2: Commit**

---

### Task 2.7: Chat Router (rag-serving/api/routers/chat.py)

**Files:**
- Create: `rag-serving/api/routers/chat.py`

**Step 1: Adapt from existing `app/api/routes/chat.py`**

Key changes:
- Use hybrid_search + reranker instead of dense-only search
- Add graph_context to prompt
- Log to query_logs table
- RBAC: department-based (remove auth_level filter)

**Step 2: Commit**

---

### Task 2.8: Admin Router (rag-serving/api/routers/admin.py)

**Files:**
- Create: `rag-serving/api/routers/admin.py`

**Step 1: Adapt from existing `app/api/routes/admin.py`**

Add new endpoints:
- `GET /admin/queries` — query_logs with filters
- `GET /admin/pipeline-logs` — pipeline_logs with filters
- `GET /admin/stats/daily` — daily query volume
- `GET /admin/stats/files` — file status breakdown

**Step 2: Commit**

---

### Task 2.9: Admin HTML Dashboard (rag-serving/admin/index.html)

**Files:**
- Create: `rag-serving/admin/index.html`

Single HTML + vanilla JS + Chart.js with tabs:
1. Query Logs table (filterable)
2. Pipeline Logs table (filterable)
3. Stats: daily query volume line chart, avg latency, file status pie chart, top users

**Step 1: Write admin HTML**

**Step 2: Commit**

---

### Task 2.10: Serving Main App (rag-serving/api/main.py)

**Files:**
- Create: `rag-serving/api/main.py`

```python
# rag-serving/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from rag_serving.api.routers import auth, chat, admin

app = FastAPI(title="RAG Serving API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])

# Serve admin HTML
app.mount("/admin", StaticFiles(directory="rag_serving/admin", html=True), name="admin")


@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 2: Commit**

---

### Task 2.11: vLLM Start Script (rag-serving/vllm/start_vllm.sh)

**Files:**
- Create: `rag-serving/vllm/start_vllm.sh`

```bash
#!/bin/bash
python -m vllm.entrypoints.openai.api_server \
    --model ${VLLM_MODEL_DIR:-/models/llm} \
    --served-model-name ${VLLM_MODEL_NAME:-qwen2.5-72b} \
    --tensor-parallel-size ${TP_SIZE:-1} \
    --quantization ${VLLM_QUANTIZATION:-awq} \
    --dtype bfloat16 \
    --gpu-memory-utilization ${VLLM_GPU_MEM_UTIL:-0.90} \
    --max-model-len ${VLLM_MAX_MODEL_LEN:-32768} \
    --host 0.0.0.0 \
    --port 8000
```

**Step 2: Commit**

---

### Task 2.12: Serving Docker (rag-serving/Dockerfile.api, docker-compose.yml)

**Files:**
- Create: `rag-serving/Dockerfile.api`
- Create: `rag-serving/docker-compose.yml`
- Create: `rag-serving/requirements.txt`

**Step 1: Write Dockerfile and compose with api + vllm services**

**Step 2: Commit**

---

## Phase 3: rag-sync-monitor

### Task 3.1: File Syncer (rag-sync-monitor/sync/file_syncer.py)

**Files:**
- Create: `rag-sync-monitor/sync/file_syncer.py`

Connects to source via SFTP/NFS, scans directories, computes checksums, compares with `document` table, writes summary to `sync_logs`.

**Step 1: Write file syncer**

Uses paramiko for SFTP or direct filesystem access for NFS mounts. Adapts from existing `app/pipeline/sync.py`.

**Step 2: Commit**

---

### Task 3.2: User Syncer (rag-sync-monitor/sync/user_syncer.py)

**Files:**
- Create: `rag-sync-monitor/sync/user_syncer.py`

LDAP/CSV user sync → upsert into `users` table.

**Step 1: Write user syncer**

**Step 2: Commit**

---

### Task 3.3: Change Detector (rag-sync-monitor/sync/change_detector.py)

**Files:**
- Create: `rag-sync-monitor/sync/change_detector.py`

Detects added/modified/deleted files, updates `document` status, returns pending doc_ids.

**Step 1: Write change detector**

**Step 2: Commit**

---

### Task 3.4: Pipeline Trigger (rag-sync-monitor/trigger/pipeline_trigger.py)

**Files:**
- Create: `rag-sync-monitor/trigger/pipeline_trigger.py`

After sync: collect pending doc_ids → POST to rag-pipeline API.

```python
# rag-sync-monitor/trigger/pipeline_trigger.py
import logging
import httpx
from shared.db import get_session
from shared.models.orm import Document

logger = logging.getLogger(__name__)

PIPELINE_API_URL = "http://rag-pipeline:8001"


def trigger_pending_documents(pipeline_url: str = PIPELINE_API_URL):
    """Find all pending/modified documents and trigger pipeline processing."""
    with get_session() as session:
        docs = session.query(Document.doc_id).filter(
            Document.status.in_(["pending", "processing"])
        ).all()
        doc_ids = [d.doc_id for d in docs]

    if not doc_ids:
        logger.info("No pending documents to process")
        return

    response = httpx.post(
        f"{pipeline_url}/pipeline/trigger",
        json={"doc_ids": doc_ids},
        timeout=30.0,
    )
    response.raise_for_status()
    logger.info("Triggered pipeline for %d documents", len(doc_ids))
```

**Step 2: Commit**

---

### Task 3.5: Scheduler (rag-sync-monitor/scheduler/cron_sync.py)

**Files:**
- Create: `rag-sync-monitor/scheduler/cron_sync.py`

APScheduler or Celery Beat for periodic sync.

**Step 1: Write scheduler**

**Step 2: Commit**

---

### Task 3.6: Streamlit Dashboard (rag-sync-monitor/dashboard/app.py)

**Files:**
- Create: `rag-sync-monitor/dashboard/app.py`

Pages:
1. Users — paginated dataframe, filter by department/role/active
2. Files — paginated dataframe, filter by status/type/department
3. Sync History — sync_logs table + timeline chart
4. File Status — pie chart (pending/processing/indexed/failed)
5. Department Breakdown — bar chart (indexed files per dept)
6. Errors — failed pipeline_logs

```python
# rag-sync-monitor/dashboard/app.py
import streamlit as st
import pandas as pd
from shared.db import get_engine

st.set_page_config(page_title="RAG Sync Monitor", layout="wide")

engine = get_engine()

page = st.sidebar.selectbox("Page", [
    "Users", "Files", "Sync History", "File Status", "Department", "Errors"
])

if page == "Users":
    st.header("Users")
    df = pd.read_sql("""
        SELECT u.user_id, u.usr_name, u.email, d.name AS department,
               r.role_name, u.is_active, u.last_login, u.created_at
        FROM users u
        JOIN department d ON u.dept_id = d.dept_id
        JOIN roles r ON u.role_id = r.role_id
        ORDER BY u.created_at DESC
    """, engine)
    dept_filter = st.selectbox("Department", ["All"] + df["department"].unique().tolist())
    if dept_filter != "All":
        df = df[df["department"] == dept_filter]
    st.dataframe(df, use_container_width=True)

elif page == "Files":
    st.header("Documents")
    df = pd.read_sql("""
        SELECT doc.doc_id, doc.file_name, doc.type, doc.status,
               d.name AS department, doc.created_at
        FROM document doc
        JOIN department d ON doc.dept_id = d.dept_id
        ORDER BY doc.created_at DESC
    """, engine)
    status_filter = st.selectbox("Status", ["All", "pending", "processing", "indexed", "failed"])
    if status_filter != "All":
        df = df[df["status"] == status_filter]
    st.dataframe(df, use_container_width=True)

elif page == "Sync History":
    st.header("Sync History")
    df = pd.read_sql("SELECT * FROM sync_logs ORDER BY started_at DESC LIMIT 100", engine)
    st.dataframe(df, use_container_width=True)
    if not df.empty:
        chart_data = df[["started_at", "files_added", "files_modified", "files_deleted"]].set_index("started_at")
        st.bar_chart(chart_data)

elif page == "File Status":
    st.header("File Status Distribution")
    df = pd.read_sql("SELECT status, COUNT(*) AS count FROM document GROUP BY status", engine)
    st.bar_chart(df.set_index("status"))

elif page == "Department":
    st.header("Indexed Files per Department")
    df = pd.read_sql("""
        SELECT d.name AS department, COUNT(*) AS count
        FROM document doc
        JOIN department d ON doc.dept_id = d.dept_id
        WHERE doc.status = 'indexed'
        GROUP BY d.name
    """, engine)
    st.bar_chart(df.set_index("department"))

elif page == "Errors":
    st.header("Pipeline Errors")
    df = pd.read_sql("""
        SELECT pl.id, doc.file_name, pl.stage, pl.status,
               pl.error_message, pl.started_at
        FROM pipeline_logs pl
        JOIN document doc ON pl.doc_id = doc.doc_id
        WHERE pl.status = 'failed'
        ORDER BY pl.started_at DESC
        LIMIT 100
    """, engine)
    st.dataframe(df, use_container_width=True)
```

**Step 2: Commit**

---

### Task 3.7: Sync Monitor Docker

**Files:**
- Create: `rag-sync-monitor/Dockerfile`
- Create: `rag-sync-monitor/docker-compose.yml`
- Create: `rag-sync-monitor/requirements.txt`

**Step 1: Write Dockerfile and compose**

**Step 2: Commit**

---

## Phase 4: Frontend Updates

### Task 4.1: Update Next.js API URLs

**Files:**
- Modify: `frontend/` — update API base URL to point to rag-serving

The API contract remains the same (same auth/chat/admin endpoints), so frontend changes are minimal. Update `NEXT_PUBLIC_API_URL` to rag-serving's port.

**Step 1: Update .env and API client config**

**Step 2: Commit**

---

## Phase 5: Root Docker Compose

### Task 5.1: Root Orchestration Compose

**Files:**
- Create: `docker-compose.yml` (root, replaces existing)

Combines all services with proper networking.

```yaml
# docker-compose.yml (root)
include:
  - docker-compose.base.yml

services:
  # rag-pipeline services
  pipeline-api:
    build:
      context: .
      dockerfile: rag-pipeline/Dockerfile
    container_name: rag-pipeline-api
    command: uvicorn rag_pipeline.api.main:app --host 0.0.0.0 --port 8001
    ports:
      - "8001:8001"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  pipeline-worker:
    build:
      context: .
      dockerfile: rag-pipeline/Dockerfile
    container_name: rag-pipeline-worker
    command: celery -A rag_pipeline.tasks.celery_app worker --loglevel=info -Q pipeline --concurrency=2
    env_file: .env
    volumes:
      - ${DOC_WATCH_DIR:-/data/documents}:/data/documents:ro
      - ${EMBEDDING_MODEL_DIR:-/data/models/embedding}:/models/embedding:ro
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  mineru-api:
    build:
      context: .
      dockerfile: Dockerfile.mineru
    container_name: rag-mineru-api
    env_file: .env
    ports:
      - "9000:9000"
    volumes:
      - ${DOC_WATCH_DIR:-/data/documents}:/data/documents:ro
      - ${MINERU_MODEL_DIR:-/data/models/mineru}:/root/.cache/mineru
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped

  # rag-serving services
  serving-api:
    build:
      context: .
      dockerfile: rag-serving/Dockerfile.api
    container_name: rag-serving-api
    command: uvicorn rag_serving.api.main:app --host 0.0.0.0 --port 8002
    ports:
      - "8002:8002"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

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
      --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
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
    profiles:
      - gpu

  # rag-sync-monitor
  sync-dashboard:
    build:
      context: .
      dockerfile: rag-sync-monitor/Dockerfile
    container_name: rag-sync-dashboard
    command: streamlit run rag_sync_monitor/dashboard/app.py --server.port=8003
    ports:
      - "8003:8003"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  # Frontend
  frontend:
    build:
      context: ./frontend
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8002}
    container_name: rag-frontend
    ports:
      - "3000:3000"
    depends_on:
      - serving-api
    restart: unless-stopped
```

**Step 2: Commit**

---

## Phase 6: Cleanup

### Task 6.1: Update .gitignore

Add entries for new project directories, data dirs, model caches.

### Task 6.2: Update CLAUDE.md

Update project memory with new v2 architecture.

### Task 6.3: Final Integration Commit

```bash
git add -A
git commit -m "feat: complete RAG-LLM v2 monorepo restructure"
```

---

## Implementation Order Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 0 | 0.1-0.8 | Directory structure, SQL, shared config/models/DB |
| 1 | 1.1-1.11 | rag-pipeline (scanner→indexer→graph→orchestrator→Celery→API→Docker) |
| 2 | 2.1-2.12 | rag-serving (retriever+RRF→reranker→graph→generator→auth/chat/admin→HTML→Docker) |
| 3 | 3.1-3.7 | rag-sync-monitor (syncer→trigger→scheduler→Streamlit→Docker) |
| 4 | 4.1 | Frontend URL updates |
| 5 | 5.1 | Root docker-compose orchestration |
| 6 | 6.1-6.3 | Cleanup and final commit |

**Total: ~35 tasks across 6 phases**
