# ERD (Entity-Relationship Diagram)

PostgreSQL 27 테이블 + 2 뷰. `shared/sql/init.sql` 기준.

```mermaid
erDiagram
    %% ===== Auth Domain =====
    department {
        SERIAL dept_id PK
        INTEGER parent_dept_id FK
        VARCHAR name UK
        TIMESTAMPTZ created_at
    }

    roles {
        SERIAL role_id PK
        VARCHAR role_name UK
        INTEGER auth_level
        TIMESTAMPTZ created_at
    }

    users {
        SERIAL user_id PK
        TEXT pwd
        VARCHAR usr_name
        VARCHAR email UK
        INTEGER dept_id FK
        INTEGER role_id FK
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ last_login
        INTEGER pwd_day
        INTEGER failure
        TIMESTAMPTZ locked_until
        BOOLEAN is_active
    }

    refresh_token {
        SERIAL id PK
        INTEGER user_id FK
        TEXT token_hash
        TIMESTAMPTZ expires_at
        BOOLEAN revoked
        TIMESTAMPTZ created_at
        VARCHAR ip_address
    }

    user_preference {
        INTEGER user_id PK_FK
        JSONB preferences
    }

    %% ===== Document Domain =====
    doc_folder {
        SERIAL folder_id PK
        INTEGER parent_folder_id FK
        VARCHAR folder_name
        TEXT folder_path
        INTEGER dept_id FK
        TIMESTAMPTZ created_at
    }

    folder_access {
        SERIAL access_id PK
        INTEGER user_id FK
        INTEGER folder_id FK
        BOOLEAN is_recursive
        INTEGER granted_by FK
        TIMESTAMPTZ granted_at
        TIMESTAMPTZ expires_at
        BOOLEAN is_active
    }

    document {
        SERIAL doc_id PK
        INTEGER folder_id FK
        VARCHAR file_name
        TEXT path
        VARCHAR type
        VARCHAR hash UK
        BIGINT size
        INTEGER dept_id FK
        INTEGER role_id FK
        INTEGER total_page_cnt
        VARCHAR language
        INTEGER version
        VARCHAR status
        TEXT error_msg
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    doc_image {
        SERIAL image_id PK
        INTEGER doc_id FK
        INTEGER page_number
        TEXT image_path
        VARCHAR image_type
        INTEGER width
        INTEGER height
        TEXT description
        TIMESTAMPTZ created_at
    }

    doc_chunk {
        SERIAL chunk_id PK
        INTEGER doc_id FK
        INTEGER chunk_idx
        TEXT content
        INTEGER token_cnt
        INTEGER page_number
        VECTOR_1024 embedding
        TSVECTOR tsv
        VARCHAR embed_model
        VARCHAR chunk_type
        INTEGER image_id FK
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    graph_entities {
        SERIAL id PK
        INTEGER doc_id FK
        TEXT entity_name
        VARCHAR entity_type
        TEXT neo4j_node_id
        TIMESTAMPTZ created_at
    }

    %% ===== Chat Domain =====
    chat_session {
        SERIAL session_id PK
        INTEGER ws_id FK
        INTEGER created_by FK
        VARCHAR title
        VARCHAR session_type
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    session_participant {
        SERIAL id PK
        INTEGER session_id FK
        INTEGER user_id FK
        VARCHAR role
        TIMESTAMPTZ joined_at
    }

    chat_msg {
        SERIAL msg_id PK
        INTEGER session_id FK
        INTEGER user_id FK
        VARCHAR sender_type
        TEXT message
        TIMESTAMPTZ created_at
    }

    msg_ref {
        SERIAL ref_id PK
        INTEGER msg_id FK
        INTEGER doc_id FK
        INTEGER chunk_id FK
        VARCHAR web_url
        FLOAT relevance_score
    }

    %% ===== Workspace Domain =====
    workspace {
        SERIAL ws_id PK
        VARCHAR ws_name
        INTEGER owner_dept_id FK
        INTEGER created_by FK
        TIMESTAMPTZ created_at
        BOOLEAN is_active
    }

    ws_permission {
        SERIAL permission_id PK
        INTEGER ws_id FK
        INTEGER user_id FK
        VARCHAR role
    }

    ws_invitation {
        SERIAL invite_id PK
        INTEGER ws_id FK
        INTEGER inviter_id FK
        INTEGER invitee_id FK
        VARCHAR status
        TIMESTAMPTZ created_at
        TIMESTAMPTZ responded_at
    }

    access_request {
        SERIAL req_id PK
        INTEGER user_id FK
        INTEGER target_ws_id FK
        VARCHAR status
        INTEGER approve_id FK
        TIMESTAMPTZ created_at
        TIMESTAMPTZ resolved_at
    }

    %% ===== Logging Domain =====
    audit_log {
        SERIAL log_id PK
        INTEGER user_id FK
        VARCHAR action_type
        VARCHAR target_type
        INTEGER target_id
        TEXT description
        VARCHAR ip_address
        TIMESTAMPTZ created_at
    }

    pipeline_logs {
        SERIAL id PK
        INTEGER doc_id FK
        VARCHAR stage
        VARCHAR status
        TIMESTAMPTZ started_at
        TIMESTAMPTZ finished_at
        TEXT error_message
        JSONB metadata
    }

    sync_logs {
        SERIAL id PK
        VARCHAR sync_type
        VARCHAR source_ip
        TIMESTAMPTZ started_at
        TIMESTAMPTZ finished_at
        INTEGER files_added
        INTEGER files_modified
        INTEGER files_deleted
        INTEGER users_added
        VARCHAR status
        TEXT error_message
    }

    query_logs {
        SERIAL id PK
        INTEGER user_id FK
        INTEGER session_id FK
        TEXT prompt
        JSONB retrieved_chunks
        JSONB reranked_chunks
        JSONB graph_context
        TEXT final_answer
        VARCHAR model_name
        INTEGER latency_ms
        INTEGER token_count_in
        INTEGER token_count_out
        TIMESTAMPTZ created_at
    }

    web_search_log {
        SERIAL id PK
        INTEGER user_id FK
        INTEGER session_id FK
        TEXT query
        BOOLEAN was_blocked
        TEXT block_reason
        INTEGER results_count
        TIMESTAMPTZ created_at
    }

    %% ===== System Domain =====
    llm_config {
        SERIAL id PK
        VARCHAR model_name
        VARCHAR vllm_url
        TEXT system_prompt
        INTEGER max_tokens
        FLOAT temperature
        FLOAT top_p
        INTEGER context_chunks
        BOOLEAN is_active
        TIMESTAMPTZ created_at
    }

    system_job {
        SERIAL job_id PK
        VARCHAR job_name
        VARCHAR job_type
        VARCHAR status
        JSONB config_json
        TIMESTAMPTZ last_run_at
        TIMESTAMPTZ next_run_at
        TEXT last_error
    }

    system_health {
        SERIAL id PK
        VARCHAR service_name
        VARCHAR status
        FLOAT response_time_ms
        JSONB metadata_json
        TIMESTAMPTZ checked_at
    }

    %% ===== Relationships =====

    %% Auth
    department ||--o{ department : "parent"
    department ||--o{ users : "dept_id"
    roles ||--o{ users : "role_id"
    users ||--o{ refresh_token : "user_id"
    users ||--o| user_preference : "user_id"

    %% Document
    department ||--o{ doc_folder : "dept_id"
    doc_folder ||--o{ doc_folder : "parent"
    doc_folder ||--o{ document : "folder_id"
    doc_folder ||--o{ folder_access : "folder_id"
    users ||--o{ folder_access : "user_id"
    department ||--o{ document : "dept_id"
    roles ||--o{ document : "role_id"
    document ||--o{ doc_image : "doc_id"
    document ||--o{ doc_chunk : "doc_id"
    document ||--o{ graph_entities : "doc_id"
    doc_image ||--o{ doc_chunk : "image_id"

    %% Chat
    users ||--o{ chat_session : "created_by"
    workspace ||--o{ chat_session : "ws_id"
    chat_session ||--o{ session_participant : "session_id"
    users ||--o{ session_participant : "user_id"
    chat_session ||--o{ chat_msg : "session_id"
    users ||--o{ chat_msg : "user_id"
    chat_msg ||--o{ msg_ref : "msg_id"
    document ||--o{ msg_ref : "doc_id"
    doc_chunk ||--o{ msg_ref : "chunk_id"

    %% Workspace
    department ||--o{ workspace : "owner_dept_id"
    users ||--o{ workspace : "created_by"
    workspace ||--o{ ws_permission : "ws_id"
    users ||--o{ ws_permission : "user_id"
    workspace ||--o{ ws_invitation : "ws_id"
    users ||--o{ ws_invitation : "inviter_id"
    users ||--o{ ws_invitation : "invitee_id"
    workspace ||--o{ access_request : "target_ws_id"
    users ||--o{ access_request : "user_id"

    %% Logging
    users ||--o{ audit_log : "user_id"
    document ||--o{ pipeline_logs : "doc_id"
    users ||--o{ query_logs : "user_id"
    chat_session ||--o{ query_logs : "session_id"
    users ||--o{ web_search_log : "user_id"
    chat_session ||--o{ web_search_log : "session_id"
```

## 도메인별 테이블 요약

### Auth (5 테이블)

| 테이블 | 설명 |
|--------|------|
| `department` | 부서 (계층 구조, self-referencing) |
| `roles` | 역할 (저장만, 접근 제어 미사용) |
| `users` | 사용자 (계정 잠금, 비밀번호 만료) |
| `refresh_token` | JWT Refresh Token (해시 저장, revoke 지원) |
| `user_preference` | 사용자 UI 설정 (JSONB) |

### Document (6 테이블)

| 테이블 | 설명 |
|--------|------|
| `doc_folder` | 문서 폴더 (계층 구조) |
| `folder_access` | 폴더 접근 권한 (만료일, 재귀) |
| `document` | 문서 메타데이터 (상태: pending/processing/indexed/failed) |
| `doc_image` | 문서 내 추출 이미지 |
| `doc_chunk` | 문서 청크 (pgvector 1024-dim + tsvector) |
| `graph_entities` | Neo4j 노드 매핑 |

### Chat (4 테이블)

| 테이블 | 설명 |
|--------|------|
| `chat_session` | 채팅 세션 (private/group) |
| `session_participant` | 세션 참여자 |
| `chat_msg` | 채팅 메시지 (user/assistant) |
| `msg_ref` | 메시지 참조 (문서/청크/웹 URL, 관련도 점수) |

### Workspace (4 테이블)

| 테이블 | 설명 |
|--------|------|
| `workspace` | 워크스페이스 (향후 API 구현 예정) |
| `ws_permission` | 워크스페이스 권한 |
| `ws_invitation` | 워크스페이스 초대 |
| `access_request` | 접근 요청 |

### Logging (5 테이블)

| 테이블 | 설명 |
|--------|------|
| `audit_log` | 감사 로그 (모든 API 요청) |
| `pipeline_logs` | 파이프라인 단계별 로그 (mineru_parse/chunk/embed/graph_extract/index) |
| `sync_logs` | 동기화 이력 (file/user/full/incremental) |
| `query_logs` | RAG 쿼리 상세 (retrieved/reranked chunks, latency, tokens) |
| `web_search_log` | 웹 검색 감사 (차단 여부 포함) |

### System (3 테이블)

| 테이블 | 설명 |
|--------|------|
| `llm_config` | LLM 설정 (system_prompt, temperature, max_tokens) |
| `system_job` | 시스템 작업 스케줄 |
| `system_health` | 서비스 상태 체크 |

### Views (2)

| 뷰 | 설명 |
|----|------|
| `user_activity_summary` | 사용자별 활동 요약 (쿼리 수, 마지막 활동) |
| `document_stats` | 문서별 통계 (청크 수, 상태, 부서) |
