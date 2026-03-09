# System Flowcharts

시스템 전체 흐름도 모음.

---

## 1. 전체 시스템 아키텍처

서비스 간 상호작용 전체 흐름.

```mermaid
graph TB
    subgraph External
        NAS[NAS / 파일 서버]
        USER[사용자 브라우저]
    end

    subgraph Frontend
        NEXT[Next.js :3000]
    end

    subgraph rag-serving [:8002]
        AUTH[Auth Router]
        CHAT[Chat Router]
        ADMIN[Admin Router]
        RET[Retriever<br/>Hybrid Search]
        RERANK[Reranker<br/>BGE-reranker-v2-m3]
        GRAPH_R[Graph Retriever]
        GEN[Generator<br/>SSE Stream]
    end

    subgraph rag-pipeline [:8001]
        PAPI[Pipeline API]
        ORC[Orchestrator]
        PARSE[MinerU Parser]
        CHUNK[Chunker]
        EMBED[Embedder<br/>BGE-M3]
        INDEX[Indexer]
        GRAPH_E[Graph Extractor]
        CELERY[Celery Worker]
    end

    subgraph rag-sync-monitor
        SCHED[APScheduler]
        FSYNC[File Syncer]
        DETECT[Change Detector]
        TRIG[Pipeline Trigger]
        DASH[Streamlit :8003]
    end

    subgraph Infrastructure
        PG[(PostgreSQL 16<br/>pgvector + tsvector)]
        NEO[(Neo4j 5<br/>APOC)]
        REDIS[(Redis 7)]
        VLLM[vLLM :8000<br/>Qwen2.5-72B]
        MINERU[MinerU :9000]
    end

    USER --> NEXT
    NEXT -->|REST + SSE| AUTH
    NEXT -->|REST + SSE| CHAT
    NEXT -->|REST| ADMIN

    CHAT --> RET
    RET -->|Dense + Sparse| PG
    RET --> RERANK
    RERANK --> GRAPH_R
    GRAPH_R -->|2-hop query| NEO
    GRAPH_R --> GEN
    GEN -->|OpenAI API| VLLM
    AUTH -->|JWT verify| PG

    PAPI -->|enqueue| REDIS
    REDIS -->|dequeue| CELERY
    CELERY --> ORC
    ORC --> PARSE
    PARSE -->|OCR| MINERU
    ORC --> CHUNK
    ORC --> EMBED
    ORC --> INDEX
    INDEX --> PG
    ORC --> GRAPH_E
    GRAPH_E --> NEO

    NAS -.->|mount| FSYNC
    SCHED --> FSYNC
    FSYNC --> DETECT
    DETECT --> PG
    DETECT --> TRIG
    TRIG -->|POST /pipeline/trigger| PAPI
    DASH -->|read-only| PG
```

---

## 2. 문서 인제스트 파이프라인

`rag-pipeline` 문서 처리 상세 흐름.

```mermaid
flowchart TD
    START([문서 처리 시작]) --> CHECK{document 테이블<br/>상태 확인}
    CHECK -->|pending| PROC[status → processing]
    CHECK -->|processing/indexed| SKIP([스킵])

    PROC --> PARSE[MinerU Parse]
    PARSE -->|OCR + 레이아웃 분석| TEXT[텍스트 + 이미지 추출]
    PARSE -->|실패| FAIL

    TEXT --> CHUNK[Hybrid Chunking]
    CHUNK -->|시맨틱 + 토큰 기반<br/>512 tokens, 50 overlap| CHUNKS[청크 리스트]
    CHUNK -->|실패| FAIL

    CHUNKS --> EMPTY{청크 0개?}
    EMPTY -->|예| DONE_EMPTY[status → indexed<br/>page_count 저장]
    EMPTY -->|아니오| EMBED

    EMBED[BGE-M3 Embed]
    EMBED -->|batch=32<br/>1024-dim vectors| VECS[임베딩 벡터]
    EMBED -->|실패| FAIL

    VECS --> INDEX[pgvector Index]
    INDEX -->|HNSW insert<br/>tsvector 자동 생성| PG[(PostgreSQL)]
    INDEX -->|실패| FAIL

    PG --> GRAPH[Graph Extract]
    GRAPH -->|NER 엔티티 추출| NEO[(Neo4j)]
    GRAPH -->|실패| FAIL

    NEO --> DONE[status → indexed<br/>page_count 저장]

    FAIL([status → failed<br/>error_msg 기록])

    style START fill:#e1f5fe
    style DONE fill:#c8e6c9
    style DONE_EMPTY fill:#c8e6c9
    style FAIL fill:#ffcdd2
```

### 각 단계별 pipeline_logs 기록

| stage | 설명 |
|-------|------|
| `mineru_parse` | MinerU OCR 파싱 (pages 수 기록) |
| `chunk` | 텍스트 청킹 (chunk 수 기록) |
| `embed` | BGE-M3 임베딩 |
| `index` | pgvector 인덱싱 |
| `graph_extract` | Neo4j 엔티티 추출 (entity 수 기록) |

---

## 3. RAG 질의 흐름

`rag-serving` 채팅 질의응답 상세 흐름.

```mermaid
flowchart TD
    START([사용자 질의]) --> AUTH{JWT 인증}
    AUTH -->|실패| ERR401([401 Unauthorized])
    AUTH -->|성공| SESSION{세션 확인}
    SESSION -->|없음| ERR404([404 Not Found])
    SESSION -->|있음| HISTORY[최근 20개 메시지 로드]

    HISTORY --> EMBED[BGE-M3 쿼리 임베딩]

    EMBED --> SEARCH{Parallel Search}
    SEARCH --> DENSE[Dense Search<br/>pgvector cosine similarity]
    SEARCH --> SPARSE[Sparse Search<br/>tsvector ts_rank]

    DENSE --> RBAC[RBAC 필터]
    SPARSE --> RBAC
    RBAC -->|dept_id + folder_access| RRF[RRF Merge<br/>k=60]

    RRF --> RERANK[BGE-reranker-v2-m3<br/>top-20 → top-5]

    RERANK --> GRAPH[Neo4j Graph Context<br/>NER → 2-hop 탐색]

    GRAPH --> PROMPT[프롬프트 빌드<br/>system + context + graph + history + query]

    PROMPT --> STREAM[vLLM SSE Stream]

    STREAM -->|token 이벤트| CLIENT[클라이언트 스트리밍]
    STREAM -->|완료| SAVE

    SAVE[DB 저장]
    SAVE --> MSG_U[user 메시지 저장]
    SAVE --> MSG_A[assistant 메시지 저장]
    SAVE --> REFS[msg_ref 참조 저장]
    SAVE --> QLOG[query_logs 기록]
    SAVE --> ALOG[audit_log 기록]
    SAVE --> DONE_EVT[done 이벤트 전송]

    style START fill:#e1f5fe
    style CLIENT fill:#e8f5e9
    style ERR401 fill:#ffcdd2
    style ERR404 fill:#ffcdd2
```

### SSE 이벤트 순서

```
1. data: {"type": "token", "content": "..."} (N회 반복)
2. data: {"type": "references", "refs": [...]}
3. data: {"type": "done", "msg_id": 42}
```

---

## 4. 파일 동기화 흐름

`rag-sync-monitor` 파일 동기화 상세 흐름.

```mermaid
flowchart TD
    START([APScheduler 트리거<br/>30분 주기]) --> SCAN[파일 시스템 스캔<br/>SOURCE_SCAN_PATHS]

    SCAN --> HASH[각 파일 SHA-256 해시 계산]

    HASH --> COMPARE{DB 해시 비교}
    COMPARE -->|해시 없음| NEW[신규 파일]
    COMPARE -->|해시 변경| MOD[수정 파일]
    COMPARE -->|DB에만 존재| DEL[삭제 파일]
    COMPARE -->|동일| SKIP([스킵])

    NEW --> REG[document 테이블 등록<br/>status = pending]
    MOD --> UPD[document 테이블 갱신<br/>status = pending, version++]
    DEL --> MARK[document 상태 변경<br/>또는 삭제]

    REG --> LOG[sync_logs 기록<br/>files_added/modified/deleted]
    UPD --> LOG
    MARK --> LOG

    LOG --> CHECK{신규 doc_ids<br/>존재?}
    CHECK -->|예| TRIGGER[POST /pipeline/trigger<br/>rag-pipeline API]
    CHECK -->|아니오| DONE([동기화 완료])
    TRIGGER --> DONE

    style START fill:#e1f5fe
    style TRIGGER fill:#fff3e0
    style DONE fill:#c8e6c9
```

---

## 5. 인증 흐름

JWT 기반 인증/인가 상세 흐름.

```mermaid
flowchart TD
    subgraph Login
        L_START([POST /auth/login]) --> L_CHECK{이메일 조회}
        L_CHECK -->|없음| L_ERR([401 Invalid credentials])
        L_CHECK -->|있음| L_LOCK{계정 잠금?}
        L_LOCK -->|잠금| L_ERR_LOCK([403 Account locked])
        L_LOCK -->|정상| L_PWD{비밀번호 검증}
        L_PWD -->|불일치| L_FAIL[failure++ 증가]
        L_FAIL --> L_FIVE{failure >= 5?}
        L_FIVE -->|예| L_DO_LOCK[locked_until = now + 30분]
        L_FIVE -->|아니오| L_ERR
        L_DO_LOCK --> L_ERR
        L_PWD -->|일치| L_RESET[failure = 0<br/>last_login = now]
        L_RESET --> L_TOKEN[Access Token 생성 (15분)<br/>Refresh Token 생성 (7일)]
        L_TOKEN --> L_SAVE[refresh_token 해시 DB 저장]
        L_SAVE --> L_RESP([200 TokenResponse])
    end

    subgraph Refresh
        R_START([POST /auth/refresh]) --> R_DECODE{refresh token 디코드}
        R_DECODE -->|만료/무효| R_ERR([401 Invalid token])
        R_DECODE -->|유효| R_DB{DB 해시 확인<br/>revoked = false?}
        R_DB -->|없음/revoked| R_ERR
        R_DB -->|유효| R_NEW[새 Access Token 발급]
        R_NEW --> R_RESP([200 AccessTokenResponse])
    end

    subgraph Protected API
        P_START([Bearer Token 헤더]) --> P_DECODE{access token 디코드}
        P_DECODE -->|만료/무효| P_ERR([401 Unauthorized])
        P_DECODE -->|유효| P_USER[DB에서 사용자 조회]
        P_USER --> P_ACTIVE{is_active?}
        P_ACTIVE -->|비활성| P_ERR
        P_ACTIVE -->|활성| P_OK([인증 완료 → 요청 처리])
    end

    style L_RESP fill:#c8e6c9
    style R_RESP fill:#c8e6c9
    style P_OK fill:#c8e6c9
    style L_ERR fill:#ffcdd2
    style L_ERR_LOCK fill:#ffcdd2
    style R_ERR fill:#ffcdd2
    style P_ERR fill:#ffcdd2
```

### 토큰 정책

| 항목 | 값 |
|------|-----|
| Access Token 만료 | 15분 |
| Refresh Token 만료 | 7일 |
| 알고리즘 | HS256 |
| 로그인 실패 잠금 | 5회 실패 → 30분 잠금 |
| Refresh Token 저장 | DB 해시 저장 (revoke 지원) |
