# RAG-LLM Enterprise Monorepo

문서 기반 RAG (Retrieval-Augmented Generation) 시스템 — 8개 모듈로 분리된 마이크로서비스.  
한국어 + 영어 문서 (PDF, Word, Excel, HWP, PPT) → 임베딩 → 하이브리드 검색 → LLM 답변.

---

## 목차
1. [시스템 개요](#1-시스템-개요)
2. [모듈 구성](#2-모듈-구성)
3. [빠른 시작](#3-빠른-시작)
4. [모듈별 동작](#4-모듈별-동작)
5. [개발 워크플로](#5-개발-워크플로)
6. [배포](#6-배포)
7. [관측성](#7-관측성)
8. [운영 환경 사양](#8-운영-환경-사양)
9. [디렉토리 구조](#9-디렉토리-구조)
10. [기여](#10-기여)
11. [라이선스](#11-라이선스)

---

## 1. 시스템 개요

### 1.1 아키텍처

```
        [Documents]
            ↓
   ┌────────────────┐  daily 02:00 (APScheduler)
   │ M2 doc-to-md   │ ── kordoc ──> Markdown files
   └────────┬───────┘
            ↓ HTTP
   ┌────────────────┐
   │ M3 chunk-embed │ ── BAAI/bge-m3 ──> PostgreSQL (pgvector + tsvector)
   └────────────────┘                              ↑
                                                   │ SELECT
   [User]                                          │
     ↓                                             │
   M6 UI ── M5 Gateway ──> M4 RAG ─────────────────┘
              │                ↓
              ├─> M1 Identity  vLLM (OpenAI 호환)
              ├─> M7 Admin
              └─> M8 Web Search
```

### 1.2 핵심 기능

| 기능 | 내용 |
|------|------|
| 하이브리드 검색 | pgvector (cosine) + tsvector (BM25) + RRF fusion |
| 인증 | JWT HS256, refresh rotation + theft detection, argon2id |
| 외부 동기화 | MySQL HR 시스템 → M1 Postgres, 60분 주기 pull |
| 관측성 | Prometheus + Grafana + Loki + Alertmanager |
| Mock 토글 | `MODULE_IMPL=mock` / `NEXT_PUBLIC_USE_MOCKS=1` |

---

## 2. 모듈 구성

| 모듈 | 책임 | 주요 기술 | 포트 |
|------|------|----------|------|
| **M1 identity** | 사용자, 인증, RBAC, MySQL 동기화 | FastAPI, asyncpg, asyncmy, APScheduler | 8001 |
| **M2 doc-to-md** | 문서 → Markdown 변환 (cron 02:00) | kordoc, APScheduler, Redis lock | 8002 |
| **M3 chunk-embed** | 청킹 + bge-m3 임베딩 + pgvector 저장 | sentence-transformers, asyncpg | 8003 |
| **M4 rag** | 하이브리드 검색 + vLLM 스트리밍 | pgvector, RRF, vLLM | 8004 |
| **M5 gateway** | 라우팅, 인증, rate limit, circuit breaker | httpx, Redis | 8005 |
| **M6 ui** | 사용자 채팅 UI | Next.js 14, TypeScript, SSE | 3000 |
| **M7 admin** | 관리자 대시보드 (BE + FE) | FastAPI + Next.js | 8007 / 3001 |
| **M8 web-search** | 외부 검색 + DLP + SSRF 차단 | httpx, ipaddress | 8008 |

각 모듈은 자체 OpenAPI 스펙을 `packages/contracts/` 에 보유 (M6 제외).

---

## 3. 빠른 시작

### 3.1 사전 준비

- Docker 24.0+ + Docker Compose v2
- Python 3.11+
- Node.js 20+ (M6, M7 frontend)
- (선택) NVIDIA Container Toolkit — GPU 사용 시

### 3.2 Secrets 생성

```bash
mkdir -p infra/secrets
for n in jwt_secret postgres_password neo4j_password grafana_password; do
  openssl rand -base64 48 > infra/secrets/$n
  chmod 600 infra/secrets/$n
done
```

### 3.3 환경변수 설정

```bash
cp .env.example .env
# 필수: POSTGRES_URL, REDIS_URL, JWT_SECRET (32자+), VLLM_URL
```

### 3.4 전체 스택 기동

```bash
make bootstrap      # 백엔드 모듈 + shared-py editable 설치
make install-fe     # Frontend npm install
make migrate        # Alembic 스키마 적용 (M1, M3)
make up             # 전체 스택 (Postgres + Redis + 8 modules)
```

기동 확인:

```bash
make ps
curl http://localhost:8005/health   # M5 gateway
curl http://localhost:3000          # M6 UI
```

### 3.5 Mock 모드 (DB/모델 없이)

```bash
make up-mock   # MODULE_IMPL=mock 전체, 인프라(PG/Redis)만 실제
```

---

## 4. 모듈별 동작

### 4.1 공통 패턴 (백엔드 M1/M2/M3/M4/M5/M7-BE/M8)

```bash
cd modules/<module-name>
make help          # 타깃 목록
make install       # shared-py + 모듈 editable 설치
make run / run-mock / test / test-cov / lint / fmt / build / clean
```

### 4.2 모듈별 특이사항

**M1 identity** (포트 8001)
```bash
cd modules/m1-identity
make migrate                       # 7개 테이블 + 역할 시드
make migrate-new name="add_xxx"    # 새 migration 생성
make run
# MySQL 동기화 1회 수동 실행
curl -X POST http://localhost:8001/admin/sync/mysql \
  -H "Authorization: Bearer <admin_token>"
```

**M2 doc-to-md** (포트 8002)
```bash
cd modules/m2-doc-to-md
make pipeline       # 점진적 1회 실행
make pipeline-full  # 강제 전체 재처리
make run            # HTTP API + APScheduler 02:00 cron 기동
```

**M3 chunk-embed** (포트 8003)
```bash
cd modules/m3-chunk-embed
make migrate    # pgvector ext + chunks/documents 테이블 + ivfflat 인덱스
make run        # 첫 요청 시 BAAI/bge-m3 자동 fetch (인터넷 필요)
```

**M4 rag** (포트 8004) — vLLM 서버 필요
```bash
# vLLM 별도 기동 예시
docker run --gpus all -p 8000:8000 vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct

cd modules/m4-rag
VLLM_URL=http://localhost:8000/v1 make run

# SSE 스트리밍 테스트
curl -N -X POST "http://localhost:8004/rag/query?stream=1" \
  -H 'Content-Type: application/json' \
  -d '{"query": "...", "top_k": 5}'
```

**M5 gateway** (포트 8005) — 외부 진입점
```bash
cd modules/m5-gateway
make run   # 모든 사용자 요청은 :8005 경유
```

**M6 ui** (포트 3000) — 사용자 채팅
```bash
cd modules/m6-ui
make install
make run                          # localhost:3000 (real mode)
NEXT_PUBLIC_USE_MOCKS=1 npm run dev  # MSW mock mode (백엔드 불필요)
make build                        # 프로덕션 빌드
```

**M7 admin** — Backend + Frontend 분리
```bash
cd modules/m7-admin/backend  && make run   # 포트 8007
cd modules/m7-admin/frontend && make run   # 포트 3001
```

**M8 web-search** (포트 8008)
```bash
cd modules/m8-web-search
make run
make search-once Q="p53 phase 2 clinical trial" PROVIDER=curated
# 선택 provider: curated(기본, offline) | brave | exa | searxng
```

---

## 5. 개발 워크플로

### 5.1 Contract-first

1. `packages/contracts/<m>.openapi.yaml` 수정 (OpenAPI SSOT)
2. `make contracts-validate` → 모듈 구현 수정 → `make contracts-lock`

### 5.2 Mock 토글로 부분 개발

```bash
make up-mock                      # 전체 mock
docker compose -f infra/docker-compose.yml stop m3-chunk-embed
MODULE_IMPL=real docker compose -f infra/docker-compose.yml up -d --no-deps m3-chunk-embed
```

### 5.3 MySQL 동기화 (M1)

필수 env: `MYSQL_URL`, `MYSQL_TABLE_USERS`, `MYSQL_TABLE_ROLES`, `MYSQL_TABLE_DEPARTMENTS`  
기본값: 60분 주기(`MYSQL_SYNC_INTERVAL_MINUTES`), 1000건 배치(`MYSQL_SYNC_BATCH_SIZE`)

### 5.4 테스트

```bash
make test          # 모든 백엔드 pytest
make test-fe       # M6/M7-fe vitest
make test-e2e      # testcontainers 통합 (Docker 필요)
make test-all      # unit + e2e 전체
cd modules/<m> && make test-cov
```

---

## 6. 배포

### 6.1 이미지 빌드

```bash
make build-images          # 전체
cd modules/<m> && make build  # 모듈별
```

### 6.2 환경변수 검증

```bash
make env-check   # JWT_SECRET, POSTGRES_URL, REDIS_URL, VLLM_URL 존재 확인
```

### 6.3 GitHub Actions

- `ci.yml` (push/PR): lint + test + contracts-diff
- `image-build.yml` (main): GHCR push, 변경 모듈만
- `pr-checks.yml` (PR): schemathesis + bandit + safety + gitleaks

### 6.4 백업

```bash
make backup-all   # pg_dump + neo4j-admin dump → backups/
```

자동: `infra/cron/backup.sh` 를 호스트 cron 등록 (30일 retention).

---

## 7. 관측성

### 7.1 스택 기동

```bash
make obs-up   # Prometheus + Grafana + Loki + Promtail + Alertmanager
```

| 서비스 | URL |
|--------|-----|
| Grafana | http://localhost:3001 (admin / `infra/secrets/grafana_password`) |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |

### 7.2 메트릭 / 알림

- 모든 백엔드 `/metrics` 노출 (M5는 Basic Auth 보호)
- 사전 정의 알림: `HighErrorRate`(>5%), `HighP99Latency`(>3s), `M1SyncFailure`, `DiskUsageHigh`, `CircuitBreakerOpen`

### 7.3 부하 테스트

```bash
LOAD_HOST=http://localhost:8005 make load-test   # 100u / 30분 / 200qpm
make load-spike                                  # 0→200 over 30s
# 결과: loadtest/results/sustained_*.csv
```

---

## 8. 운영 환경 사양

| 항목 | 기준 |
|------|------|
| OS | Ubuntu 24.04 LTS |
| GPU | 1/4 NVIDIA (M3 임베딩 + M4 query embedding 공유) |
| RAM | 512 GB |
| 동시 사용자 | 100 |
| 분당 쿼리 | 200 qpm |
| PostgreSQL | pgvector/pgvector:pg16 |
| Redis | 7 (appendonly) |
| Neo4j | 5 (선택, Graph RAG용) |

---

## 9. 디렉토리 구조

```
.
├── modules/            # M1~M8 마이크로서비스 (각 Makefile 보유)
│   ├── m1-identity/    m2-doc-to-md/    m3-chunk-embed/    m4-rag/
│   ├── m5-gateway/     m6-ui/           m7-admin/{backend,frontend}/
│   └── m8-web-search/
├── packages/
│   ├── contracts/      # OpenAPI SSOT (7 YAML + .sha256 락)
│   └── shared-py/      # 공통 config / db / http / logging
├── infra/
│   ├── docker-compose.{yml,base,mock,observability}.yml
│   ├── secrets/        observability/    cron/
├── tests-e2e/          # testcontainers 통합 테스트
├── loadtest/           # locust 시나리오
├── scripts/            # contracts-lock / contracts-verify
├── .github/workflows/  # CI/CD (ci, image-build, pr-checks)
└── Makefile            # 루트 오케스트레이션
```

---

## 10. 기여

브랜치: `feat/<module>/<description>` → `make test && make lint` → PR  
PR 시 GitHub Actions (lint / test / contracts-diff) 자동 검증.  
CODEOWNERS: `.github/CODEOWNERS`

---

## 11. 라이선스

MIT
