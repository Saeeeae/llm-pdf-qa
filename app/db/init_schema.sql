-- =============================================================================
-- PostgreSQL Database Schema Initialization
-- On-Premise LLM & RAG System v2
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. Department - Hierarchical organization structure
-- =============================================================================
CREATE TABLE IF NOT EXISTS department (
    dept_id SERIAL PRIMARY KEY,
    parent_dept_id INTEGER REFERENCES department(dept_id) ON DELETE SET NULL,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_department_parent ON department(parent_dept_id);

-- =============================================================================
-- 2. Roles - Role definitions with authorization levels
-- =============================================================================
CREATE TABLE IF NOT EXISTS roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL UNIQUE,
    auth_level INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 3. Users - Authentication & RBAC
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

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_dept_id ON users(dept_id);
CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id);

-- =============================================================================
-- 4. Doc Folder - Hierarchical folder structure
-- =============================================================================
CREATE TABLE IF NOT EXISTS doc_folder (
    folder_id SERIAL PRIMARY KEY,
    parent_folder_id INTEGER REFERENCES doc_folder(folder_id) ON DELETE CASCADE,
    folder_name VARCHAR(255) NOT NULL,
    folder_path TEXT NOT NULL,
    dept_id INTEGER NOT NULL REFERENCES department(dept_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_doc_folder_parent ON doc_folder(parent_folder_id);
CREATE INDEX IF NOT EXISTS idx_doc_folder_dept ON doc_folder(dept_id);
CREATE INDEX IF NOT EXISTS idx_doc_folder_path ON doc_folder(folder_path);

-- =============================================================================
-- 5. Folder Access - Granular folder-level access control
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_folder_access_user_folder ON folder_access(user_id, folder_id);
CREATE INDEX IF NOT EXISTS idx_folder_access_folder ON folder_access(folder_id);

-- =============================================================================
-- 6. Workspace - Collaboration spaces
-- =============================================================================
CREATE TABLE IF NOT EXISTS workspace (
    ws_id SERIAL PRIMARY KEY,
    ws_name VARCHAR(200) NOT NULL,
    owner_dept_id INTEGER NOT NULL REFERENCES department(dept_id) ON DELETE RESTRICT,
    created_by INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_workspace_owner_dept ON workspace(owner_dept_id);
CREATE INDEX IF NOT EXISTS idx_workspace_created_by ON workspace(created_by);

-- =============================================================================
-- 7. Workspace Permission
-- =============================================================================
CREATE TABLE IF NOT EXISTS ws_permission (
    permission_id SERIAL PRIMARY KEY,
    ws_id INTEGER NOT NULL REFERENCES workspace(ws_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_permission_ws_user ON ws_permission(ws_id, user_id);

-- =============================================================================
-- 8. Workspace Invitation
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

CREATE INDEX IF NOT EXISTS idx_ws_invitation_invitee ON ws_invitation(invitee_id, status);

-- =============================================================================
-- 9. Chat Session
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

CREATE INDEX IF NOT EXISTS idx_chat_session_ws ON chat_session(ws_id);
CREATE INDEX IF NOT EXISTS idx_chat_session_created_by ON chat_session(created_by);

-- =============================================================================
-- 10. Session Participant - Multi-user collaboration
-- =============================================================================
CREATE TABLE IF NOT EXISTS session_participant (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_session_participant_session_user ON session_participant(session_id, user_id);

-- =============================================================================
-- 11. Document - File metadata with folder & RBAC
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
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_msg TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_document_folder ON document(folder_id, status);
CREATE INDEX IF NOT EXISTS idx_document_hash ON document(hash);
CREATE INDEX IF NOT EXISTS idx_document_dept_role ON document(dept_id, role_id);
CREATE INDEX IF NOT EXISTS idx_document_status ON document(status);
CREATE INDEX IF NOT EXISTS idx_document_created_at ON document(created_at DESC);

-- =============================================================================
-- 12. Doc Chunk - Document chunks for RAG
-- =============================================================================
CREATE TABLE IF NOT EXISTS doc_chunk (
    chunk_id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES document(doc_id) ON DELETE CASCADE,
    chunk_idx INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_cnt INTEGER DEFAULT 0,
    page_number INTEGER,
    qdrant_id VARCHAR(64),
    embed_model VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_doc_chunk_doc ON doc_chunk(doc_id, chunk_idx);
CREATE INDEX IF NOT EXISTS idx_doc_chunk_qdrant ON doc_chunk(qdrant_id);

-- =============================================================================
-- 13. Chat Message
-- =============================================================================
CREATE TABLE IF NOT EXISTS chat_msg (
    msg_id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES chat_session(session_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    sender_type VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_msg_session ON chat_msg(session_id, created_at);

-- =============================================================================
-- 14. Message Reference - RAG source tracking
-- =============================================================================
CREATE TABLE IF NOT EXISTS msg_ref (
    ref_id SERIAL PRIMARY KEY,
    msg_id INTEGER NOT NULL REFERENCES chat_msg(msg_id) ON DELETE CASCADE,
    doc_id INTEGER REFERENCES document(doc_id) ON DELETE SET NULL,
    chunk_id INTEGER REFERENCES doc_chunk(chunk_id) ON DELETE SET NULL,
    web_url VARCHAR(2048),
    relevance_score FLOAT
);

CREATE INDEX IF NOT EXISTS idx_msg_ref_msg ON msg_ref(msg_id);

-- =============================================================================
-- 15. Access Request - Workspace access requests
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

CREATE INDEX IF NOT EXISTS idx_access_request_status ON access_request(status);

-- =============================================================================
-- 16. Audit Log - Universal activity tracking
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

CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);

-- =============================================================================
-- 17. System Job - Background job scheduler
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

CREATE INDEX IF NOT EXISTS idx_system_job_type ON system_job(job_type);

-- =============================================================================
-- 18. System Health - Service health monitoring
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_health (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_time_ms FLOAT,
    metadata_json JSONB,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_system_health_service ON system_health(service_name);
CREATE INDEX IF NOT EXISTS idx_system_health_checked_at ON system_health(checked_at DESC);

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

DO $$ BEGIN
    CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER update_document_updated_at BEFORE UPDATE ON document
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER update_doc_chunk_updated_at BEFORE UPDATE ON doc_chunk
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TRIGGER update_chat_session_updated_at BEFORE UPDATE ON chat_session
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- =============================================================================
-- Initial Seed Data
-- =============================================================================
INSERT INTO department (name) VALUES ('Admin'), ('Research'), ('Clinical_Team'), ('QA')
    ON CONFLICT (name) DO NOTHING;

INSERT INTO roles (role_name, auth_level) VALUES
    ('Admin', 100),
    ('Manager', 50),
    ('Member', 10),
    ('Viewer', 1)
    ON CONFLICT (role_name) DO NOTHING;

-- =============================================================================
-- Views for Analytics
-- =============================================================================
CREATE OR REPLACE VIEW user_activity_summary AS
SELECT
    u.user_id,
    u.usr_name,
    d.name AS department,
    r.role_name,
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
    doc.doc_id,
    doc.file_name,
    d.name AS department,
    r.role_name,
    df.folder_name,
    doc.status,
    COUNT(dc.chunk_id) AS chunk_count,
    doc.created_at
FROM document doc
JOIN department d ON doc.dept_id = d.dept_id
JOIN roles r ON doc.role_id = r.role_id
LEFT JOIN doc_folder df ON doc.folder_id = df.folder_id
LEFT JOIN doc_chunk dc ON doc.doc_id = dc.doc_id
GROUP BY doc.doc_id, doc.file_name, d.name, r.role_name, df.folder_name, doc.status, doc.created_at;
