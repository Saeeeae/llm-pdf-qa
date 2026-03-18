-- =============================================================================
-- PostgreSQL Database Schema Initialization
-- On-Premise RAG-LLM System v2
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 1. Department
CREATE TABLE IF NOT EXISTS department (
    dept_id SERIAL PRIMARY KEY,
    parent_dept_id INTEGER REFERENCES department(dept_id) ON DELETE SET NULL,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_department_parent ON department(parent_dept_id);

-- 2. Roles (stored only, NOT used for access control)
CREATE TABLE IF NOT EXISTS roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL UNIQUE,
    auth_level INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Users
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

-- 4. Refresh Token
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

-- 5. User Preference
CREATE TABLE IF NOT EXISTS user_preference (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    preferences JSONB DEFAULT '{"search_scope": "all", "web_search": false, "theme": "light"}'
);

-- 6. Doc Folder
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

-- 7. Folder Access
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

-- 8. Workspace
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

-- 9. Workspace Permission
CREATE TABLE IF NOT EXISTS ws_permission (
    permission_id SERIAL PRIMARY KEY,
    ws_id INTEGER NOT NULL REFERENCES workspace(ws_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer'
);
CREATE UNIQUE INDEX idx_ws_permission_ws_user ON ws_permission(ws_id, user_id);

-- 10. Workspace Invitation
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

-- 11. Chat Session
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

-- 12. Session Participant
CREATE TABLE IF NOT EXISTS session_participant (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX idx_session_participant_session_user ON session_participant(session_id, user_id);

-- 13. Document
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

-- 14. Doc Image
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

-- 15. Doc Chunk (vector store with pgvector + tsvector)
CREATE TABLE IF NOT EXISTS doc_block (
    block_id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    block_idx INTEGER NOT NULL,
    block_type VARCHAR(30) NOT NULL DEFAULT 'text',
    page_number INTEGER,
    sheet_name VARCHAR(255),
    slide_number INTEGER,
    section_path TEXT,
    language VARCHAR(10) DEFAULT 'ko',
    bbox JSONB,
    source_text TEXT NOT NULL,
    normalized_text TEXT,
    parent_block_id INTEGER REFERENCES doc_block(block_id) ON DELETE SET NULL,
    image_id INTEGER REFERENCES doc_image(image_id) ON DELETE SET NULL,
    metadata_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_doc_block_doc ON doc_block(doc_id, block_idx);
CREATE INDEX idx_doc_block_type ON doc_block(block_type);
CREATE INDEX idx_doc_block_page ON doc_block(doc_id, page_number);
CREATE INDEX idx_doc_block_norm ON doc_block USING gin(to_tsvector('simple', coalesce(normalized_text, source_text)));

-- 16. Doc Chunk (vector store with pgvector + tsvector)
CREATE TABLE IF NOT EXISTS doc_chunk (
    chunk_id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    block_id INTEGER REFERENCES doc_block(block_id) ON DELETE SET NULL,
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
CREATE INDEX idx_doc_chunk_block ON doc_chunk(block_id);
CREATE INDEX idx_chunks_embedding ON doc_chunk USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_chunks_tsv ON doc_chunk USING gin(tsv);

-- 17. Graph Entities
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

-- 18. Entity Alias
CREATE TABLE IF NOT EXISTS entity_alias (
    id SERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    alias_type VARCHAR(50) DEFAULT 'domain',
    language VARCHAR(10) DEFAULT 'ko',
    boost FLOAT DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (normalized_alias, canonical_name)
);
CREATE INDEX idx_entity_alias_norm ON entity_alias(normalized_alias);
CREATE INDEX idx_entity_alias_canonical ON entity_alias(canonical_name);

-- 19. Doc Keyword
CREATE TABLE IF NOT EXISTS doc_keyword (
    id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    chunk_id INTEGER NOT NULL REFERENCES doc_chunk(chunk_id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    normalized_keyword TEXT NOT NULL,
    keyword_type VARCHAR(50) DEFAULT 'token',
    weight FLOAT DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_doc_keyword_norm ON doc_keyword(normalized_keyword);
CREATE INDEX idx_doc_keyword_doc ON doc_keyword(doc_id, chunk_id);

-- 20. Chat Message
CREATE TABLE IF NOT EXISTS chat_msg (
    msg_id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    sender_type VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_chat_msg_session ON chat_msg(session_id, created_at);

-- 21. Message Reference
CREATE TABLE IF NOT EXISTS msg_ref (
    ref_id SERIAL PRIMARY KEY,
    msg_id INTEGER NOT NULL REFERENCES chat_msg(msg_id) ON DELETE CASCADE,
    doc_id INTEGER REFERENCES document(doc_id) ON DELETE SET NULL,
    chunk_id INTEGER REFERENCES doc_chunk(chunk_id) ON DELETE SET NULL,
    web_url VARCHAR(2048),
    relevance_score FLOAT
);
CREATE INDEX idx_msg_ref_msg ON msg_ref(msg_id);

-- 22. Access Request
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

-- 22. Audit Log
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

-- 23. LLM Config
CREATE TABLE IF NOT EXISTS llm_config (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    vllm_url VARCHAR(255) NOT NULL DEFAULT 'http://vllm-server:8000/v1',
    system_prompt TEXT DEFAULT '당신은 사내 문서를 기반으로 답변하는 AI 어시스턴트입니다. 제공된 문서 내용을 바탕으로 정확하고 도움이 되는 답변을 제공하세요.',
    max_tokens INTEGER DEFAULT 4096,
    temperature FLOAT DEFAULT 0.7,
    top_p FLOAT DEFAULT 0.9,
    context_chunks INTEGER DEFAULT 5,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 24. Web Search Log
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

-- 25. Pipeline Logs
CREATE TABLE IF NOT EXISTS pipeline_logs (
    id SERIAL PRIMARY KEY,
    doc_id INTEGER REFERENCES document(doc_id) ON DELETE CASCADE,
    stage VARCHAR(30) NOT NULL CHECK (stage IN ('mineru_parse','chunk','embed','graph_extract','index')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('running','success','failed')),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metadata JSONB
);
CREATE INDEX idx_pipeline_logs_doc ON pipeline_logs(doc_id);
CREATE INDEX idx_pipeline_logs_status ON pipeline_logs(status);

-- 26. Sync Logs
CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(20) CHECK (sync_type IN ('user','file','full','incremental')),
    source_ip VARCHAR(45),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    files_added INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    users_added INTEGER DEFAULT 0,
    status VARCHAR(20) CHECK (status IN ('running','success','failed')),
    error_message TEXT
);
CREATE INDEX idx_sync_logs_status ON sync_logs(status);

-- 27. Query Logs
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

-- 28. System Job
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

-- 29. System Health
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

-- 28. Event Log (general-purpose extensible event log for all modules)
CREATE TABLE IF NOT EXISTS event_log (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(32),
    module VARCHAR(30) NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    severity VARCHAR(10) NOT NULL,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES chat_session(session_id) ON DELETE SET NULL,
    doc_id INTEGER REFERENCES document(doc_id) ON DELETE SET NULL,
    message TEXT NOT NULL,
    details JSONB,
    duration_ms INTEGER,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_event_log_trace ON event_log(trace_id);
CREATE INDEX idx_event_log_module ON event_log(module);
CREATE INDEX idx_event_log_event_type ON event_log(event_type);
CREATE INDEX idx_event_log_severity ON event_log(severity);
CREATE INDEX idx_event_log_created_at ON event_log(created_at DESC);
CREATE INDEX idx_event_log_module_type ON event_log(module, event_type);
CREATE INDEX idx_event_log_user ON event_log(user_id);
CREATE INDEX idx_event_log_doc ON event_log(doc_id);

-- Triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_document_updated_at BEFORE UPDATE ON document FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_doc_block_updated_at BEFORE UPDATE ON doc_block FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_doc_chunk_updated_at BEFORE UPDATE ON doc_chunk FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_chat_session_updated_at BEFORE UPDATE ON chat_session FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Seed Data
INSERT INTO department (name) VALUES ('Admin'), ('Research'), ('Clinical_Team'), ('QA') ON CONFLICT (name) DO NOTHING;
INSERT INTO roles (role_name, auth_level) VALUES ('Admin', 100), ('Manager', 50), ('Member', 10), ('Viewer', 1) ON CONFLICT (role_name) DO NOTHING;
INSERT INTO entity_alias (canonical_name, alias, normalized_alias, alias_type, language, boost) VALUES
('milestone', 'milestone', 'milestone', 'business', 'en', 1.15),
('milestone', '마일스톤', '마일스톤', 'business', 'ko', 1.15),
('upfront', 'upfront', 'upfront', 'business', 'en', 1.15),
('upfront', '계약금', '계약금', 'business', 'ko', 1.15),
('term sheet', 'term sheet', 'term sheet', 'business', 'en', 1.10),
('term sheet', '텀싯', '텀싯', 'business', 'ko', 1.10),
('preclinical', 'preclinical', 'preclinical', 'drug_dev', 'en', 1.10),
('preclinical', '비임상', '비임상', 'drug_dev', 'ko', 1.10),
('clinical', 'clinical', 'clinical', 'drug_dev', 'en', 1.05),
('clinical', '임상', '임상', 'drug_dev', 'ko', 1.05),
('efficacy', 'efficacy', 'efficacy', 'drug_dev', 'en', 1.10),
('efficacy', '유효성', '유효성', 'drug_dev', 'ko', 1.10),
('safety', 'safety', 'safety', 'drug_dev', 'en', 1.10),
('safety', '안전성', '안전성', 'drug_dev', 'ko', 1.10),
('target', 'target', 'target', 'drug_dev', 'en', 1.10),
('target', '타깃', '타깃', 'drug_dev', 'ko', 1.10),
('target', '타겟', '타겟', 'drug_dev', 'ko', 1.10),
('indication', 'indication', 'indication', 'drug_dev', 'en', 1.10),
('indication', '적응증', '적응증', 'drug_dev', 'ko', 1.10),
('nsclc', 'NSCLC', 'nsclc', 'drug_dev', 'en', 1.20),
('nsclc', '비소세포폐암', '비소세포폐암', 'drug_dev', 'ko', 1.20),
('cmc', 'CMC', 'cmc', 'drug_dev', 'en', 1.05),
('cmc', '제조품질', '제조품질', 'drug_dev', 'ko', 1.05)
ON CONFLICT (normalized_alias, canonical_name) DO NOTHING;
INSERT INTO llm_config (model_name, vllm_url, is_active) VALUES ('qwen2.5-72b', 'http://vllm-server:8000/v1', TRUE);

-- Views
CREATE OR REPLACE VIEW user_activity_summary AS
SELECT u.user_id, u.usr_name, d.name AS department, r.role_name,
    COUNT(al.log_id) AS total_actions,
    COUNT(al.log_id) FILTER (WHERE al.action_type = 'query') AS total_queries,
    MAX(al.created_at) AS last_activity
FROM users u
JOIN department d ON u.dept_id = d.dept_id
JOIN roles r ON u.role_id = r.role_id
LEFT JOIN audit_log al ON u.user_id = al.user_id
GROUP BY u.user_id, u.usr_name, d.name, r.role_name;

CREATE OR REPLACE VIEW document_stats AS
SELECT doc.doc_id, doc.file_name, d.name AS department, r.role_name,
    df.folder_name, doc.status,
    COUNT(dc.chunk_id) AS chunk_count, doc.created_at
FROM document doc
JOIN department d ON doc.dept_id = d.dept_id
JOIN roles r ON doc.role_id = r.role_id
LEFT JOIN doc_folder df ON doc.folder_id = df.folder_id
LEFT JOIN doc_chunk dc ON doc.doc_id = dc.doc_id
GROUP BY doc.doc_id, doc.file_name, d.name, r.role_name, df.folder_name, doc.status, doc.created_at;

-- Permissions (safe: only grant if role exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'admin') THEN
        EXECUTE 'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin';
        EXECUTE 'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO admin';
        EXECUTE 'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO admin';
    END IF;
END
$$;
