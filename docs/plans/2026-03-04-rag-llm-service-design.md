# RAG-LLM 사내 AI 서비스 설계 문서

**작성일:** 2026-03-04
**프로젝트:** On-Premise RAG-LLM 통합 서비스
**목표:** 사내 문서 기반 ChatGPT/Claude 수준의 AI 어시스턴트 구축 (완전 온프레미스)

---

## 1. 프로젝트 개요

### 현재 상태 (Phase 0 — 완료)
- 문서(PDF, DOCX, XLSX, PPTX, 이미지) → OCR → Chunking → Embedding → PostgreSQL + Qdrant
- 매일 02:00 자동 동기화 (신규/수정/삭제/이동 감지)
- FastAPI 전처리 API 제공

### 목표 상태 (Phase 1~3)
사내 임직원이 ChatGPT처럼 사내 문서를 기반으로 질문하고 답변받는 완전 온프레미스 AI 어시스턴트.
외부 API(OpenAI, Anthropic 등) 미사용 — 보안 최우선.

---

## 2. 전체 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│              Next.js Frontend (port 3000)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │  Login   │ │  Chat UI │ │  Docs    │ │  Admin   │  │
│  │  Page    │ │ (stream) │ │ Manager  │ │  Panel   │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API + SSE (streaming)
┌───────────────────────▼─────────────────────────────────┐
│              FastAPI Backend (port 8000)                 │
│  /auth/*  /chat/*  /search/*  /processing/*  /admin/*   │
└──────┬──────────┬──────────┬──────────┬─────────────────┘
       │          │          │          │
  ┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐ ┌──────────┐
  │ vLLM   │ │Qdrant  │ │Postgres│ │ Redis  │ │Web Search│
  │Qwen2.5 │ │vectors │ │  DB    │ │Celery  │ │  Proxy   │
  │72B AWQ │ │        │ │        │ │        │ │(내부전용)│
  └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘

  GPU: HB200 x 1 → 추후 x 4~8 확장 (tensor_parallel_size 변경만으로)
```

### Docker 서비스 목록 (전체)

| 서비스 | 역할 | 포트 | 비고 |
|--------|------|------|------|
| `frontend` | Next.js UI | 3000 | 신규 |
| `api` | FastAPI 확장 | 8000 | 기존 확장 |
| `vllm-server` | Qwen 모델 서빙 | 8001 | 신규 |
| `postgres` | 메타데이터 + 청크 | 5432 | 기존 |
| `qdrant` | 벡터 검색 | 6333 | 기존 |
| `redis` | Celery 브로커 | 6379 | 기존 |
| `mineru-api` | OCR/PDF 파싱 | 9000 | 기존 |
| `celery-worker` | 비동기 처리 | - | 기존 |
| `celery-beat` | 스케줄러 | - | 기존 |

---

## 3. 인증 시스템 (Phase 1)

### 방식
- JWT Bearer Token (Access + Refresh)
- 기존 `users`, `roles`, `department` 테이블 활용
- 비밀번호: bcrypt 해시

### API
```
POST /api/v1/auth/login      → { access_token, refresh_token, user_info }
POST /api/v1/auth/refresh    → { access_token }
POST /api/v1/auth/logout     → refresh token 무효화
GET  /api/v1/auth/me         → 현재 사용자 정보 (dept, role 포함)
```

### 토큰 정책
- Access token: 15분 만료 (JWT, stateless)
- Refresh token: 7일 만료, DB 저장 + 해시 검증
- 로그인 실패 5회 → 계정 잠금 (`failure`, `locked_until` 컬럼 활용)
- 모든 보호 API: `Authorization: Bearer <token>` 헤더 필수

### 신규 DB 테이블
```sql
CREATE TABLE refresh_token (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address VARCHAR(45)
);
CREATE INDEX idx_refresh_token_user ON refresh_token(user_id);
CREATE INDEX idx_refresh_token_hash ON refresh_token(token_hash);
```

---

## 4. RAG-LLM Chat 서비스 (Phase 2)

### 채팅 플로우
```
사용자 메시지 입력
    ↓
[1] embed_query(message)  ← multilingual-e5-large
    ↓
[2] vector_search(embedding, filter=user_rbac)
    → dept_id + role_id + folder_access 기반 접근 가능 문서만 검색
    → top-K 청크 + 점수 반환
    ↓
[3] build_prompt(
      system_prompt,
      retrieved_chunks (컨텍스트),
      chat_history (최근 N턴),
      user_message
    )
    ↓
[4] vLLM /v1/chat/completions (stream=True, OpenAI 호환)
    ↓
[5] SSE 스트리밍 → Next.js EventSource → 실시간 렌더링
    ↓
[6] 완료 후 DB 저장:
    - chat_msg (user + assistant)
    - msg_ref (사용된 청크 + relevance_score)
    - audit_log (action_type='chat_query')
```

### API
```
POST   /api/v1/chat/sessions                   → 세션 생성
GET    /api/v1/chat/sessions                   → 내 세션 목록 (페이지네이션)
DELETE /api/v1/chat/sessions/{id}              → 세션 삭제
GET    /api/v1/chat/sessions/{id}/messages     → 대화 히스토리
POST   /api/v1/chat/sessions/{id}/stream       → SSE 스트리밍 답변
GET    /api/v1/chat/sessions/{id}/references   → 사용된 참고 문서 목록
```

### SSE 응답 형식
```json
data: {"type": "token", "content": "안녕"}
data: {"type": "token", "content": "하세요"}
data: {"type": "references", "refs": [{"doc_id": 1, "file_name": "매출보고서.pdf", "page": 3, "score": 0.92}]}
data: {"type": "done", "msg_id": 123}
```

### RBAC 검색 필터
- `role.auth_level >= 문서의 role.auth_level` 인 문서만 검색
- `folder_access` 테이블에서 사용자가 접근 권한 있는 폴더의 문서만 포함
- 검색 범위: 전체 / 내 부서 / 특정 폴더 (사용자가 선택 가능)

---

## 5. 웹 검색 프록시 (Phase 2 - 선택)

### 목적
- 외부 검색 API 쿼리가 사내 망 밖으로 나가기 전 검열/감사
- 사내 민감 정보가 외부 검색 쿼리에 포함되는 것 방지

### 플로우
```
사용자 검색 요청
    ↓
[1] 쿼리 검열: deny_list 패턴 매칭 (사내 코드명, PII 패턴 등)
    → 감지 시 검색 거부 + 경고 반환
    ↓
[2] audit_log 기록 (user_id, raw_query, timestamp)
    ↓
[3] 외부 Search API 호출 (Google Custom Search 또는 SearXNG)
    ↓
[4] 결과에서 title + snippet만 추출 (전체 페이지 내용 X)
    ↓
[5] 결과를 RAG 컨텍스트에 포함 또는 직접 반환
```

### API
```
POST /api/v1/search/web
{
  "query": "검색어",
  "session_id": "optional",
  "max_results": 5
}
```

### 보안 레벨 선택
| 방식 | 유출 위험 | 비고 |
|------|---------|------|
| Google Custom Search API (프록시) | 낮음 | 쿼리만 외부 전송 |
| SearXNG 자체 호스팅 | **없음** | Docker 1개 추가, 권장 |
| Brave Search API | 낮음 | 쿼리만 외부 전송 |

> **권장:** SearXNG 자체 호스팅 — 완전 폐쇄망 환경에서 외부 API 없이 운영 가능

---

## 6. 프론트엔드 UI (Phase 2)

### 페이지 구조
```
/login          → 로그인 페이지
/chat           → 메인 채팅 (기본 페이지)
/chat/[id]      → 특정 세션 대화
/documents      → 문서 목록 + 업로드
/admin          → 관리자 패널 (auth_level=100만 접근)
/admin/users    → 사용자 관리
/admin/docs     → 문서 관리
/admin/system   → 시스템 모니터링
/admin/logs     → 감사 로그
```

### 채팅 UI 레이아웃
```
┌─────────────────────────────────────────────────────────┐
│ 🏢 사내 AI 어시스턴트          [홍길동 | 연구팀 ▼] [설정] │
├──────────────┬──────────────────────────────────────────┤
│  대화 목록    │                                           │
│  ─────────── │  어시스턴트                               │
│  + 새 대화   │  ┌──────────────────────────────────┐    │
│  ─────────── │  │ 매출 분석 결과에 따르면...        │    │
│  오늘        │  │ [스트리밍 중...]                   │    │
│  > 매출 분석 │  └──────────────────────────────────┘    │
│  > Q3 보고서 │                                           │
│  ─────────── │  📎 참고 문서                             │
│  어제        │  • 2025_매출보고서.pdf (p.3, 유사도 0.92) │
│  > 계약 검토 │  • Q3_실적분석.xlsx (Sheet2, 0.87)       │
│              │                                           │
│              │  ─────────────────────────────────────── │
│              │  [검색 범위: 전체 ▼] [웹 검색 ON/OFF]    │
│              │  ┌──────────────────────────────── [전송]┐│
│              │  │ 메시지를 입력하세요...               ││
│              │  └─────────────────────────────────────┘│
└──────────────┴──────────────────────────────────────────┘
```

### 핵심 UX 기능
- **실시간 스트리밍**: SSE → `EventSource` → 토큰 단위 렌더링
- **참고 문서 인용**: 답변에 출처 파일명 + 페이지 번호 표시, 클릭 시 문서 뷰어
- **Markdown 렌더링**: 코드 블록 하이라이팅, 표, 수식 지원
- **검색 범위 선택**: 전체 / 내 부서 / 특정 폴더
- **웹 검색 토글**: On/Off (프록시 경유)
- **대화 히스토리**: 무제한 사이드바, 제목 자동 생성 (첫 메시지 기반)

---

## 7. Admin 시스템 (Phase 3)

### 접근 제어
- `roles.auth_level >= 100` (Admin 역할)인 사용자만 접근

### 기능 목록
| 메뉴 | 기능 |
|------|------|
| 사용자 관리 | 계정 생성/수정/비활성화, 부서/역할 변경, 비밀번호 초기화 |
| 문서 관리 | 인덱싱 현황, 재처리 트리거, 강제 삭제, 폴더 권한 설정 |
| 시스템 모니터 | Celery 작업 현황, vLLM 상태, 서비스 헬스체크 |
| 감사 로그 | audit_log 뷰어 (user/action/날짜 필터, CSV 내보내기) |
| LLM 설정 | 모델 파라미터 (temperature, max_tokens), 시스템 프롬프트 관리 |
| 동기화 설정 | 스케줄 변경, 수동 동기화 트리거 |

---

## 8. DB 변경사항

### 신규 테이블

```sql
-- 리프레시 토큰 관리
CREATE TABLE refresh_token (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address VARCHAR(45)
);

-- 사용자 UI 설정 (검색 범위 기본값, 테마 등)
CREATE TABLE user_preference (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    preferences JSONB DEFAULT '{"search_scope": "all", "web_search": false, "theme": "light"}'
);

-- LLM 모델 설정 (Admin에서 관리)
CREATE TABLE llm_config (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    vllm_url VARCHAR(255) NOT NULL DEFAULT 'http://vllm-server:8001/v1',
    system_prompt TEXT,
    max_tokens INTEGER DEFAULT 4096,
    temperature FLOAT DEFAULT 0.7,
    top_p FLOAT DEFAULT 0.9,
    context_chunks INTEGER DEFAULT 5,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 웹 검색 요청 로그 (감사용)
CREATE TABLE web_search_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES chat_session(session_id) ON DELETE SET NULL,
    query TEXT NOT NULL,
    was_blocked BOOLEAN DEFAULT FALSE,
    block_reason TEXT,
    results_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 9. vLLM 배포 설정

### 단일 GPU (현재)
```yaml
# docker-compose.yml 추가
vllm-server:
  image: vllm/vllm-openai:latest
  command: >
    python -m vllm.entrypoints.openai.api_server
    --model Qwen/Qwen2.5-72B-Instruct-AWQ
    --quantization awq
    --tensor-parallel-size 1
    --gpu-memory-utilization 0.90
    --max-model-len 32768
    --served-model-name qwen2.5-72b
  ports:
    - "8001:8000"
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

### 멀티 GPU 확장 시 (추후)
```yaml
# tensor-parallel-size만 변경
--tensor-parallel-size 4   # HB200 x 4
--tensor-parallel-size 8   # HB200 x 8
```

### 모델 옵션 (단일 HB200 141GB 기준)
| 모델 | 메모리 | 성능 | 권장 용도 |
|------|--------|------|---------|
| Qwen2.5-72B-AWQ (INT4) | ~40GB | 최고 | 운영 권장 |
| Qwen2.5-32B-FP16 | ~64GB | 우수 | 정확도 우선 |
| Qwen3-30B-A3B | ~60GB | 우수 | MoE 효율 |

---

## 10. 구현 단계 (Phases)

### Phase 1: 인증 시스템 (기반)
1. DB 마이그레이션 (refresh_token, user_preference, llm_config, web_search_log)
2. FastAPI auth 라우터 (login/refresh/logout/me)
3. JWT 미들웨어 (기존 API 보호)
4. Next.js 프로젝트 초기화 + 로그인 페이지

### Phase 2: RAG-LLM Chat
1. vLLM Docker 서비스 추가
2. FastAPI chat 라우터 (세션 CRUD + SSE 스트리밍)
3. RAG 파이프라인 (벡터 검색 → 프롬프트 빌드 → vLLM 호출)
4. RBAC 검색 필터 적용
5. 웹 검색 프록시 (SearXNG + FastAPI 프록시 레이어)
6. Next.js 채팅 UI (스트리밍, 참고 문서 인용, 사이드바)

### Phase 3: Admin 시스템
1. FastAPI admin 라우터 (사용자/문서/시스템 관리)
2. Next.js Admin 패널 UI
3. 감사 로그 뷰어

---

## 11. 기술 스택 요약

| 레이어 | 기술 |
|--------|------|
| Frontend | Next.js 14+ (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI (Python 3.11+) |
| LLM | vLLM + Qwen2.5-72B-AWQ |
| Vector DB | Qdrant (기존) + pgvector (기존) |
| RDBMS | PostgreSQL 16 (pgvector 확장) |
| Embedding | intfloat/multilingual-e5-large |
| Task Queue | Celery + Redis |
| OCR/Parsing | MinerU v2.x |
| Web Search | SearXNG (자체 호스팅) 또는 Google Custom Search |
| Container | Docker Compose |
| Auth | JWT (python-jose) + bcrypt |