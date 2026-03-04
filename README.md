# 사내 AI 어시스턴트 (On-Premise RAG-LLM)

사내 문서(PDF, DOCX, XLSX, PPTX, 이미지)를 기반으로 **ChatGPT/Claude 수준의 UX**를 제공하는 완전 온프레미스 AI 어시스턴트.
외부 API(OpenAI, Anthropic 등) 미사용 — 보안 최우선.

---

## 시스템 구성

```
┌─────────────────────────────────────────────────────────┐
│              Next.js Frontend (port 3000)               │
│         로그인 · 채팅 UI · 문서관리 · 관리자패널          │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API + SSE (실시간 스트리밍)
┌───────────────────────▼─────────────────────────────────┐
│              FastAPI Backend (port 8000)                 │
│  /auth  /chat  /processing  /documents  /search  /admin │
└──────┬──────────┬──────────┬──────────┬─────────────────┘
       │          │          │          │
  ┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐ ┌──────────┐
  │ vLLM   │ │Qdrant/ │ │Postgres│ │ Redis  │ │ Google   │
  │Qwen2.5 │ │pgvector│ │  DB    │ │Celery  │ │Search API│
  │72B AWQ │ │        │ │        │ │        │ │(프록시)  │
  └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘

  GPU: HB200 x 1 → tensor_parallel 설정으로 x 4~8 확장
```

### Docker 서비스

| 서비스 | 역할 | 포트 |
|--------|------|------|
| `frontend` | Next.js UI | 3000 |
| `api` | FastAPI 백엔드 | 8000 |
| `vllm-server` | Qwen 모델 서빙 (GPU 필요) | 8001 |
| `postgres` | 메타데이터 · 청크 · 벡터 저장 | 5432 |
| `redis` | Celery 브로커 | 6379 |
| `mineru-api` | OCR/PDF 파싱 | 9000 |
| `celery-worker` | 비동기 문서 처리 | - |
| `celery-beat` | 일일 자동 동기화 스케줄러 | - |

---

## 주요 기능

### 문서 전처리 파이프라인
- **지원 형식**: PDF, DOCX, XLSX, PPTX, PNG/JPG/TIFF
- **처리 흐름**: OCR(MinerU) → 청킹(Hybrid) → 임베딩(E5-large) → PostgreSQL 저장
- **자동 동기화**: 매일 02:00 감시 폴더 스캔 (신규/수정/삭제 문서 자동 반영)

### RAG-LLM 채팅
- ChatGPT 수준 UX — 실시간 스트리밍 응답 (SSE)
- 답변에 **참고 문서 · 페이지 번호** 인용
- **RBAC 검색 필터** — 사용자 부서/역할 기반 접근 가능 문서만 검색
- 웹 검색 연동 (Google Custom Search API 프록시, 감사 로그)

### 인증 · 보안
- JWT (Access 15분 / Refresh 7일)
- 로그인 실패 5회 → 계정 잠금 (30분)
- 모든 API 요청 감사 로그 (audit_log)
- 웹 검색 쿼리 검열 (민감 정보 패턴 차단)

### 관리자 패널
- 사용자 CRUD (부서/역할 변경, 활성화/비활성화)
- 문서 처리 현황 모니터링
- LLM 설정 관리 (system_prompt, temperature 등)
- 감사 로그 조회

---

## 빠른 시작

### 1. 환경 설정

```bash
git clone <repository-url>
cd llm_again
cp .env.example .env
```

`.env` 필수 설정:

```ini
# PostgreSQL
POSTGRES_PASSWORD=your_secure_password

# JWT (반드시 변경 — 최소 32자)
JWT_SECRET=your-very-secret-key-minimum-32-characters

# Google Custom Search API (웹 검색 사용 시)
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CX=your_custom_search_engine_id

# 문서 감시 폴더
DOC_WATCH_DIR=/path/to/your/documents
```

### 2. 서비스 실행 (GPU 없이 — 개발/전처리)

```bash
# DB + 전처리 파이프라인 + 프론트엔드
make up

# 상태 확인
make ps
```

### 3. 첫 관리자 계정 생성

```bash
docker compose exec api python3 -c "
from app.auth.password import hash_password
from app.db.models import User
from app.db.postgres import get_session
with get_session() as s:
    u = User(
        pwd=hash_password('your_password'),
        usr_name='관리자',
        email='admin@company.com',
        dept_id=1,
        role_id=1
    )
    s.add(u)
print('관리자 계정 생성 완료')
"
```

### 4. 브라우저 접속

**http://localhost:3000** 에서 로그인 후 사용

### 5. vLLM 실행 (GPU 서버)

```bash
# HuggingFace에서 모델 사전 다운로드 (선택)
huggingface-cli download Qwen/Qwen2.5-72B-Instruct-AWQ \
  --local-dir /data/models/vllm/Qwen2.5-72B-Instruct-AWQ

# GPU 서비스 시작
docker compose --profile gpu up vllm-server -d
```

---

## 문서 인제스트

### API로 직접 업로드

```bash
# 전체 파이프라인 (파싱 → 청킹 → 임베딩 → DB 저장)
curl -X POST http://localhost:8000/api/v1/processing/full-pipeline \
  -F "file=@document.pdf"
```

### 감시 폴더로 자동 처리

`DOC_WATCH_DIR`에 파일 복사 후 동기화 트리거:

```bash
make sync        # 수동 동기화
make scan        # 처리 가능한 파일 목록
make status      # 처리 현황
```

---

## API 레퍼런스

Swagger UI: **http://localhost:8000/docs**

### 인증

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/v1/auth/login` | POST | 로그인 → access/refresh token |
| `/api/v1/auth/refresh` | POST | access token 갱신 |
| `/api/v1/auth/logout` | POST | refresh token 무효화 |
| `/api/v1/auth/me` | GET | 현재 사용자 정보 |

### 채팅

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/v1/chat/sessions` | POST | 새 세션 생성 |
| `/api/v1/chat/sessions` | GET | 내 세션 목록 |
| `/api/v1/chat/sessions/{id}/stream` | POST | **SSE 스트리밍 답변** |
| `/api/v1/chat/sessions/{id}/messages` | GET | 대화 히스토리 |
| `/api/v1/chat/sessions/{id}` | DELETE | 세션 삭제 |

### 문서 처리

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/v1/processing/parse` | POST | 파싱만 (텍스트 추출) |
| `/api/v1/processing/chunk` | POST | 파싱 + 청킹 |
| `/api/v1/processing/embed` | POST | 파싱 + 청킹 + 임베딩 |
| `/api/v1/processing/full-pipeline` | POST | 전체 + DB 저장 |
| `/api/v1/processing/search` | POST | 벡터 유사도 검색 |

### 웹 검색 (프록시)

```bash
curl -X POST http://localhost:8000/api/v1/search/web \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "검색어", "max_results": 5}'
```

---

## 환경변수 전체 목록

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DOC_WATCH_DIR` | `/data/documents` | 문서 감시 폴더 |
| `POSTGRES_PASSWORD` | `changeme` | DB 비밀번호 |
| `JWT_SECRET` | *(변경 필수)* | JWT 서명 키 (32자+) |
| `JWT_ACCESS_EXPIRE_MINUTES` | `15` | Access token 만료 (분) |
| `JWT_REFRESH_EXPIRE_DAYS` | `7` | Refresh token 만료 (일) |
| `GOOGLE_API_KEY` | - | Google Custom Search API 키 |
| `GOOGLE_CX` | - | Google 커스텀 검색 엔진 ID |
| `EMBED_MODEL` | `intfloat/multilingual-e5-large` | 임베딩 모델 |
| `EMBED_DEVICE` | `cpu` | 디바이스 (cpu/cuda/mps) |
| `CHUNK_STRATEGY` | `hybrid` | 청킹 전략 |
| `CHUNK_SIZE` | `512` | 청크 최대 토큰 수 |
| `VLLM_MODEL` | `Qwen/Qwen2.5-72B-Instruct-AWQ` | vLLM 모델 |
| `VLLM_TENSOR_PARALLEL` | `1` | GPU 병렬 수 |
| `VLLM_GPU_COUNT` | `1` | GPU 개수 |
| `MINERU_BACKEND` | `pipeline` | MinerU 백엔드 |
| `SYNC_CRON_HOUR` | `2` | 자동 동기화 시각 (시) |
| `HF_TOKEN` | - | HuggingFace 토큰 |

---

## vLLM 모델 선택 (HB200 단일 GPU 기준)

| 모델 | 메모리 | 성능 | 비고 |
|------|--------|------|------|
| `Qwen/Qwen2.5-72B-Instruct-AWQ` | ~40GB | 최고 | **운영 권장** |
| `Qwen/Qwen2.5-32B-Instruct` | ~64GB | 우수 | 고정밀도 |
| `Qwen/Qwen3-30B-A3B` | ~60GB | 우수 | MoE 효율형 |

멀티 GPU 확장:
```ini
# .env
VLLM_TENSOR_PARALLEL=4   # HB200 x 4
VLLM_GPU_COUNT=4
```

---

## 프로젝트 구조

```
llm_again/
├── app/
│   ├── api/
│   │   ├── main.py              # FastAPI 앱 + CORS + 라우터
│   │   └── routes/
│   │       ├── auth.py          # 로그인/토큰/사용자 정보
│   │       ├── chat.py          # 채팅 세션 CRUD + SSE 스트리밍
│   │       ├── search.py        # Google 웹 검색 프록시
│   │       ├── admin.py         # 관리자 API
│   │       ├── processing.py    # 문서 전처리 API
│   │       └── documents.py     # 문서 CRUD + 동기화
│   ├── auth/
│   │   ├── jwt.py               # 토큰 생성/검증
│   │   ├── password.py          # bcrypt 해싱
│   │   └── dependencies.py      # FastAPI Depends (인증 미들웨어)
│   ├── chat/
│   │   └── rag_pipeline.py      # RAG 파이프라인 (검색→프롬프트→vLLM)
│   ├── db/
│   │   ├── init_schema.sql      # PostgreSQL DDL (23개 테이블)
│   │   ├── models.py            # SQLAlchemy ORM 모델
│   │   ├── postgres.py          # DB 연결
│   │   └── vector_store.py      # pgvector RBAC 검색
│   ├── parsers/                 # PDF/DOCX/XLSX/PPTX/이미지 파서
│   ├── processing/              # 청킹 · 임베딩
│   ├── pipeline/                # 인제스트 · 스캔 · 동기화
│   ├── tasks/                   # Celery 태스크
│   └── config.py                # 전체 설정 (Pydantic)
├── frontend/
│   ├── app/
│   │   ├── login/               # 로그인 페이지
│   │   ├── chat/                # 채팅 UI (레이아웃 + 세션별 페이지)
│   │   └── admin/               # 관리자 패널
│   ├── components/
│   │   ├── Sidebar.tsx          # 대화 목록 사이드바
│   │   ├── ChatMessage.tsx      # 메시지 버블 (Markdown + 참고문서)
│   │   └── ChatInput.tsx        # 입력창 (검색범위 · 웹검색 토글)
│   └── lib/
│       ├── api.ts               # Axios 클라이언트 (JWT 자동 첨부/갱신)
│       └── auth.ts              # Zustand 인증 상태
├── docs/
│   └── plans/
│       ├── 2026-03-04-rag-llm-service-design.md
│       └── 2026-03-04-rag-llm-implementation-plan.md
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## Makefile 주요 명령어

| 명령어 | 설명 |
|--------|------|
| `make up` | 전체 서비스 시작 |
| `make down` | 서비스 중지 |
| `make build` | Docker 이미지 빌드 |
| `make ps` | 컨테이너 상태 |
| `make logs` | API + Worker 로그 |
| `make status` | 문서 처리 현황 |
| `make sync` | 수동 동기화 |
| `make scan` | 처리 가능한 파일 목록 |
| `make ingest-file FILE=<path>` | 단일 파일 인제스트 |
| `make init-db` | DB 스키마 재초기화 |
| `make clean` | 전체 초기화 (볼륨 삭제) |

---

## 트러블슈팅

### DB 초기화 오류 (비밀번호 변경 후)
```bash
docker compose down -v --remove-orphans
sudo rm -rf /data/db/postgres
make up
```

### vLLM GPU 메모리 부족
`.env`에서 더 작은 모델로 변경:
```ini
VLLM_MODEL=Qwen/Qwen2.5-32B-Instruct
```

### 임베딩 모델 느린 로딩 (첫 실행)
HuggingFace에서 ~2.2GB 자동 다운로드. `hf_cache` 볼륨에 캐시되어 이후 재다운로드 불필요.

### 로그 확인
```bash
make logs-api      # API 서버 로그
make logs-worker   # Celery Worker 로그
docker compose --profile gpu logs vllm-server  # vLLM 로그
```
