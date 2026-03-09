# RAG-LLM v2 설계 문서

**작성일:** 2026-03-09
**프로젝트:** On-Premise RAG-LLM v2 (3-프로젝트 모노레포)

---

## 1. 결정사항 요약

| 항목 | 결정 |
|------|------|
| 레포 구조 | 모노레포 (rag-pipeline, rag-serving, rag-sync-monitor + shared) |
| Frontend | Next.js 유지 (rag-serving에 포함), admin 통계는 vanilla HTML |
| Workspace | 테이블만 선행 생성, API는 향후 구현 |
| Task Queue | Celery 유지 (rag-pipeline) |
| 데이터 | 클린 스타트 (Qdrant 마이그레이션 없음, BGE-M3 재임베딩) |
| RBAC | Department 기반만 (role은 저장만) |

---

## 2. 모노레포 구조

```
llm_again/
├── shared/
│   ├── sql/init.sql
│   ├── models/registry.py
│   └── config.py
├── rag-pipeline/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── pipeline/
│   │   ├── scanner.py
│   │   ├── parser.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── indexer.py
│   │   ├── graph_extractor.py
│   │   └── orchestrator.py
│   ├── tasks/
│   │   ├── celery_app.py
│   │   └── pipeline_tasks.py
│   ├── api/main.py
│   └── scheduler/cron_sync.py
├── rag-serving/
│   ├── docker-compose.yml
│   ├── Dockerfile.api
│   ├── Dockerfile.vllm
│   ├── api/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   └── admin.py
│   │   └── rag/
│   │       ├── retriever.py
│   │       ├── graph_retriever.py
│   │       ├── reranker.py
│   │       └── generator.py
│   ├── admin/index.html
│   └── vllm/start_vllm.sh
├── rag-sync-monitor/
│   ├── docker-compose.yml
│   ├── sync/
│   │   ├── user_syncer.py
│   │   ├── file_syncer.py
│   │   └── change_detector.py
│   ├── trigger/pipeline_trigger.py
│   ├── scheduler/cron_sync.py
│   └── dashboard/app.py
├── frontend/
├── docker-compose.base.yml
└── docker-compose.yml
```

---

## 3. DB 스키마

사용자 제공 18개 테이블 유지 + 아래 추가/수정:

### 추가 확장
- `CREATE EXTENSION IF NOT EXISTS vector;`

### doc_chunk 수정
- `qdrant_id` 제거
- `embedding vector(1024)` 추가 (BGE-M3)
- `tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED` 추가
- HNSW 인덱스: `CREATE INDEX idx_chunks_embedding ON doc_chunk USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);`
- GIN 인덱스: `CREATE INDEX idx_chunks_tsv ON doc_chunk USING gin(tsv);`

### 추가 테이블
- `graph_entities` — Neo4j 노드 매핑 (file_id, entity_name, entity_type, neo4j_node_id)
- `pipeline_logs` — 파이프라인 단계별 로그 (file_id, stage, status, error)
- `sync_logs` — 동기화 이력 (sync_type, files_added/modified/deleted, status)
- `query_logs` — RAG 쿼리 상세 (user_id, prompt, chunks, answer, latency, tokens)
- `refresh_token` — JWT 리프레시 토큰
- `llm_config` — LLM 설정
- `web_search_log` — 웹 검색 감사
- `user_preference` — 사용자 UI 설정

---

## 4. RBAC 모델

- Department 기반: `doc.dept_id = user.dept_id`
- folder_access로 부서 외 접근 허용
- role은 저장만, 접근 제어 미사용

---

## 5. 검색 파이프라인

```
Query → BGE-M3 embed
     → Parallel: Dense (pgvector cosine) + Sparse (tsvector ts_rank)
     → RRF merge (k=60)
     → BGE-reranker-v2-m3 (top-20 → top-5)
     → Neo4j graph context (NER → 2-hop)
     → Prompt build → vLLM SSE stream
```

---

## 6. 기술 스택

| 레이어 | 기술 |
|--------|------|
| Frontend | Next.js 14 + Vanilla HTML admin |
| Backend | FastAPI (Python 3.11) |
| LLM | vLLM + Qwen2.5-72B-AWQ |
| Embedding | BAAI/bge-m3 (1024-dim) |
| Reranker | BAAI/bge-reranker-v2-m3 |
| Vector+RDBMS | PostgreSQL 16 + pgvector (HNSW) |
| Graph DB | Neo4j 5 + APOC |
| Task Queue | Celery + Redis |
| OCR | MinerU (RAG-Anything) |
| Monitoring | Streamlit |
| Container | Docker Compose |
