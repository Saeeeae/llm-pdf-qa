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

| 모듈 | 책임 | 주요 기술 | 호스트 포트 |
|------|------|----------|------|
| **M1 identity** | 사용자, 인증, RBAC, MySQL 동기화 | FastAPI, asyncpg, asyncmy, APScheduler | 8101 |
| **M2 doc-to-md** | 문서 → Markdown 변환 (cron 02:00) | kordoc, APScheduler, Redis lock | 8102 |
| **M3 chunk-embed** | 계층 청킹 + bge-m3 임베딩 + pgvector(HNSW) | sentence-transformers, asyncpg | 8103 |
| **M4 rag** | retrieve→rerank→MMR→parent→vLLM 스트리밍 | pgvector, BGE-reranker, vLLM | 8104 |
| **M5 gateway** | 라우팅, 인증, rate limit, circuit breaker | httpx, Redis | **8080** |
| **M6 ui** | 사용자 채팅 UI | Next.js 14, TypeScript, SSE | 3000 |
| **M7 admin** | 관리자 대시보드 (BE + FE) | FastAPI + Next.js | 8107 / 3001 |
| **M8 web-search** | 외부 검색 + DLP + SSRF 차단 | httpx, ipaddress | 8108 |

> 컨테이너 내부 포트는 백엔드 모두 `8000`, 프론트엔드는 `3000` / `3001`. 위 표는 호스트로 publish되는 포트입니다.

각 모듈은 자체 OpenAPI 스펙을 `packages/contracts/` 에 보유 (M6 제외).

---

## 3. 빠른 시작

> 빌드/배포 상세는 [BUILD.md](BUILD.md) 참고.

### 3.1 사전 준비

- **Docker 24.0+** + Docker Compose v2 (필수)
- vLLM 호환 LLM 서버 — GPU 노드에서 별도 기동 (M4가 호출, [3.7](#37-vllm-기동-별도-호스트) 참고)
- (선택) Python 3.11+ — 컨테이너 안에서 다 돌아가니 호스트에 없어도 무방
- (선택) Node.js 20+ — `make run` 호스트 모드용
- (선택) NVIDIA Container Toolkit — GPU 사용 시

### 3.2 처음 시작하는 분을 위한 한 번에 끝내기

이 흐름을 그대로 따라하면 `git clone` → 채팅 가능한 상태까지 갑니다.

```bash
# 1. 저장소 클론
git clone <this-repo-url> rag-llm && cd rag-llm

# 2. 호스트 데이터 디렉토리 생성 (sudo 필요할 수 있음)
sudo make data-init                            # /data, /data2 트리 생성
sudo chown -R $(id -u):$(id -g) /data /data2   # 사용자 권한

# 3. 비밀 자동 생성 (JWT, PG, Neo4j)
make secrets-init                              # infra/secrets/* 생성

# 4. (선택) vLLM 별도 기동 — 3.7 참고. 안 띄워도 stack 자체는 동작하나
#    채팅 응답이 503으로 떨어집니다.

# 5. 전체 스택 빌드 + 기동 (단계 2,3을 자동으로 한 번 더 호출하므로 안전)
make up

# 6. DB 스키마 (컨테이너 안에서 alembic 실행 — 호스트 Python 필요 없음)
make migrate

# 7. 입력 문서 한 개 넣고 인덱싱
sudo cp ~/path/to/sample.pdf /data2/sample.pdf
sudo chown $(id -u):$(id -g) /data2/sample.pdf
cd modules/m2-doc-to-md && make docker-pipeline   # /data2 → /data/markdown → m3 → embedding

# 8. 체크
curl -f http://localhost:8080/health      # 게이트웨이
curl -f http://localhost:8104/ready       # m4 RAG (vLLM 미기동 시 503 OK)
open http://localhost:3000                # 사용자 UI
open http://localhost:3001                # 관리자 UI (admin.read 권한 필요)
```

### 3.3 호스트 데이터 디렉토리 레이아웃

영속 데이터는 호스트의 두 경로에 바인드 마운트됩니다:

| 경로 | 용도 |
|------|------|
| `DATA_ROOT` (기본 `/data`) | DB, 모델 캐시, 마크다운, state, 로그 |
| `DATA2_ROOT` (기본 `/data2`) | 원본 입력 문서 (RO) |

다른 경로를 쓰려면:
```bash
DATA_ROOT=/mnt/nvme/rag DATA2_ROOT=/mnt/nas/docs make up
```

`make data-init`이 만드는 하위 트리:
```
/data/db/{postgres,neo4j,redis}     /data/models     /data/markdown
/data/state/m2                      /data/logs/{m2,m5,m7,m8}
/data2/                             ← 여기에 PDF/DOCX 등을 넣음
```

### 3.4 첫 사용자 만들기

`make migrate`가 끝나면 `roles` 테이블엔 `admin/manager/user`가 시드되지만 **users 테이블은 비어있습니다**. 두 가지 방법:

**A. MySQL HR 시스템 동기화 (운영 권장)**
```bash
# .env 또는 컨테이너 환경변수에
MYSQL_URL=mysql+asyncmy://user:pass@hr-db:3306/hr
MYSQL_SYNC_ON_STARTUP=1
```
m1 기동 시 한 번 동기화. 자세한 옵션은 [modules/m1-identity/README.md](modules/m1-identity/README.md).

**B. 수동 부트스트랩 (개발/PoC)**
```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U postgres -d ragdb -c "
    INSERT INTO users (email, password_hash, name, role_id, is_active)
    VALUES ('admin@example.com', '\$argon2id\$...PUT-HASH-HERE...', '관리자',
            (SELECT id FROM roles WHERE name='admin'), true);
  "
```
argon2 해시는 `python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('your-password'))"`로 만드세요.

### 3.5 Mock 모드 (DB/GPU/vLLM 전부 없이 UX만 보기)

```bash
make up-mock        # 모든 모듈 MODULE_IMPL=mock, 인프라(PG/Redis)만 실제
```
브라우저에서 `http://localhost:3000` 열고 `mock@example.com / mock`으로 로그인 (Mock 핸들러가 응답).

### 3.6 단일 모듈만

```bash
make up-one m=m3-chunk-embed     # base infra + 한 모듈만 (개발 시)
make build-one m=m6-ui           # 이미지만 빌드
cd modules/m4-rag && make docker-up    # 모듈 디렉토리에서도 가능
```

### 3.7 vLLM 기동 (별도 호스트)

M4가 답변 생성을 위임하는 LLM 서버입니다. 본 compose에는 포함되지 않으므로 별도 기동:

```bash
# 동일 호스트에서 GPU로 띄울 때
docker run --rm --gpus all -p 8000:8000 \
  -v /data/models:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct --max-model-len 8192

# m4가 호출하는 주소를 알려주기
VLLM_URL=http://<vllm-host>:8000/v1 make up
```

### 3.8 정상 동작 체크리스트

| 명령 | 기대 응답 |
|------|----------|
| `make ps` | 모든 서비스 `running (healthy)` |
| `curl localhost:8080/health` | `{"status":"ok"}` |
| `curl localhost:8104/ready` | `{"status":"ready"}` (vLLM 살아있을 때) |
| `curl localhost:8101/health` | `{"status":"ok"}` |
| `localhost:3000`을 브라우저로 | 로그인 페이지 |
| 로그인 후 메시지 전송 | 토큰 단위 SSE 스트리밍 |

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

**M1 identity** (호스트 8101)
```bash
cd modules/m1-identity
make help                          # 타깃 목록
# 마이그레이션은 루트에서: make migrate
make migrate-new NAME="add_xxx"    # 새 migration 생성 (호스트 venv 필요)
make docker-up                     # 컨테이너 기동
# MySQL 동기화 수동 트리거
curl -X POST http://localhost:8101/admin/sync/mysql \
  -H "Authorization: Bearer <admin_token>"
```

**M2 doc-to-md** (호스트 8102)
```bash
cd modules/m2-doc-to-md
make docker-pipeline       # 컨테이너에서 1회 실행 (권장 — /data2 마운트 사용)
make docker-pipeline-full  # state 클리어 후 재실행
make pipeline              # 호스트 venv에서 1회 (개발 시)
```

**M3 chunk-embed** (호스트 8103)
```bash
cd modules/m3-chunk-embed
# 마이그레이션은 루트에서: make migrate
make docker-up             # 첫 기동 시 BAAI/bge-m3 약 2.3GB 다운로드 (인터넷 필요)
```

**M4 rag** (호스트 8104) — vLLM 서버 필요 ([3.7](#37-vllm-기동-별도-호스트) 참고)
```bash
cd modules/m4-rag
make docker-up             # 첫 기동 시 reranker 약 600MB 추가 다운로드

# SSE 스트리밍 테스트 (m5 게이트웨이 통해야 정상; 직접 호출은 인증 우회)
curl -N -X POST "http://localhost:8104/rag/query?stream=1" \
  -H 'Content-Type: application/json' \
  -d '{"query": "...", "top_k": 5}'
```

**M5 gateway** (호스트 8080) — 외부 진입점
```bash
cd modules/m5-gateway
make docker-up   # 모든 사용자 요청은 :8080 경유 (CORS allowlist 필수)
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
cd modules/m7-admin/backend  && make docker-up   # 호스트 8107
cd modules/m7-admin/frontend && make docker-up   # 호스트 3001
```

**M8 web-search** (호스트 8108)
```bash
cd modules/m8-web-search
make docker-up
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
make build-images               # 전체 9개 서비스
make build-one m=m4-rag         # 단일 서비스
make build-no-cache             # 처음부터 재빌드
cd modules/<m> && make build    # 모듈 디렉토리에서도 가능 (compose 기반)
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
| Grafana | http://localhost:3002 (admin / `infra/secrets/grafana_password`) |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |

> Grafana는 m7-admin 프론트엔드(3001)와 충돌하지 않도록 `infra/docker-compose.observability.yml`에서 3002로 publish합니다.

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
├── Makefile            # 루트 오케스트레이션 (`make help` 시작점)
├── BUILD.md            # 빌드/배포 상세 가이드
├── README.md           # ← 이 문서 (개요)
├── modules/            # M1~M8 마이크로서비스 (각 Makefile + Dockerfile + compose 보유)
│   ├── m1-identity/    m2-doc-to-md/    m3-chunk-embed/    m4-rag/
│   ├── m5-gateway/     m6-ui/           m7-admin/{backend,frontend}/
│   └── m8-web-search/
├── packages/
│   ├── contracts/      # OpenAPI SSOT (7 YAML + .sha256 락)
│   └── shared-py/      # 공통 config / db / http / logging (모든 백엔드 Dockerfile이 COPY)
├── infra/
│   ├── docker-compose.{yml,base,mock,observability}.yml   # `${DATA_ROOT}` 바인드 마운트
│   ├── secrets/        observability/    cron/
├── tests-e2e/          # testcontainers 통합 테스트
├── loadtest/           # locust 시나리오
├── scripts/            # contracts-lock / contracts-verify
└── .github/workflows/  # CI/CD (ci, image-build, pr-checks)
```

호스트 (저장소 외부):
```
/data/                  # DATA_ROOT — DB, 모델 캐시, 마크다운, state, 로그
/data2/                 # DATA2_ROOT — 원본 입력 문서 (RO)
```

---

## 10. 기여

브랜치: `feat/<module>/<description>` → `make test && make lint` → PR  
PR 시 GitHub Actions (lint / test / contracts-diff) 자동 검증.  
CODEOWNERS: `.github/CODEOWNERS`

---

## 11. 라이선스

MIT
