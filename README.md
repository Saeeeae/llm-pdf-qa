# RAG-LLM Enterprise Monorepo

문서 기반 RAG (Retrieval-Augmented Generation) 시스템 — 8개 모듈로 분리된 마이크로서비스.
한국어 + 영어 문서 (PDF, Word, Excel, HWP, PPT) → 임베딩 → 하이브리드 검색 → LLM 답변.

---

## 목차
1. [시스템 개요](#1-시스템-개요)
2. [모듈 구성](#2-모듈-구성)
3. [빠른 시작](#3-빠른-시작)
4. [모듈별 운영](#4-모듈별-운영)
5. [개발 워크플로](#5-개발-워크플로)
6. [관측성 / 백업](#6-관측성--백업)
7. [운영 환경 사양](#7-운영-환경-사양)
8. [디렉토리 구조](#8-디렉토리-구조)

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
| 외부 동기화 | 사내 HR DB (USER_INFO) → M1 Postgres, 60분 주기 pull, m1→m2 ordered trigger |
| 관측성 | Prometheus + Grafana + Loki + Alertmanager |
| Mock 토글 | `MODULE_IMPL=mock` (overlay) |

---

## 2. 모듈 구성

| 모듈 | 책임 | 주요 기술 | Host:Container |
|------|------|----------|----------------|
| **M1 identity** | 사용자, 인증, RBAC, MySQL 동기화, admin bootstrap | FastAPI, asyncpg, asyncmy, APScheduler | 8101:8000 |
| **M2 doc-to-md** | 문서 → Markdown, 사내 DB 파일/폴더 ACL pull | kordoc, APScheduler, Redis lock | 8102:8000 |
| **M3 chunk-embed** | 청킹 + bge-m3 임베딩 + pgvector 저장 | sentence-transformers, asyncpg | 8103:8000 |
| **M4 rag** | 하이브리드 검색 + vLLM 스트리밍 | pgvector, RRF, vLLM | 8104:8000 |
| **M5 gateway** | 라우팅, 인증, rate limit, circuit breaker | httpx, Redis | 8080:8000 |
| **M6 ui** | 사용자 채팅 UI | Next.js 14, TypeScript, SSE | 3000 |
| **M7 admin** | 관리자 대시보드 (BE + FE) | FastAPI + Next.js | 8107 / 3001 |
| **M8 web-search** | 외부 검색 + DLP + SSRF 차단 | httpx, ipaddress | 8108:8000 |

각 모듈은 OpenAPI 스펙을 `packages/contracts/`에 보유 (M6 제외).

---

## 3. 빠른 시작

> 자세한 운영 순서/검증/트러블슈팅은 [docs/RUNBOOK.md](docs/RUNBOOK.md) 참고.

### 3.1 사전 준비

- Docker 24.0+ + Docker Compose v2
- Git
- (선택) NVIDIA Container Toolkit — GPU 사용 시 (M3, M4)

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

루트 `.env`가 SSOT입니다. 모듈 `.env.example`은 stub일 뿐 컨테이너는 루트 `.env`를 읽습니다.

```bash
cp .env.example .env
# 필수: POSTGRES_PASSWORD, NEO4J_PASSWORD, JWT_SECRET (32자+),
#       INTERNAL_SYNC_TOKEN, MYSQL_URL, M2_MYSQL_FILE_URL
# 선택: BOOTSTRAP_ADMIN_EMAIL/PASSWORD (첫 admin 자동 생성)
```
브라우저에서 `http://localhost:3000` 열고 `mock@example.com / mock`으로 로그인 (Mock 핸들러가 응답).

### 3.4 부팅 시퀀스

```bash
make prepare          # 호스트 데이터/로그 디렉토리 + 권한
make build            # 모든 모듈 docker 이미지 빌드
make migrate          # alembic upgrade head — m1, m3 (admin role 시드 포함)
make run              # 전체 스택 기동 (prepare를 자동 의존)
make ps               # 헬스 확인
```

각 단계의 의미와 실패 시 디버깅은 [docs/RUNBOOK.md §1](docs/RUNBOOK.md#1-최초-배포--처음-한-번만)에 정리.

### 3.5 첫 admin 생성

`.env`에 `BOOTSTRAP_ADMIN_EMAIL`/`BOOTSTRAP_ADMIN_PASSWORD`를 미리 둔 경우 `make run` 시 자동 생성됨. 그렇지 않다면:

```bash
cd modules/m1-identity
make create-admin EMAIL=admin@example.com PASSWORD='strong-secret-32+chars'
```

### 3.6 동작 확인

```bash
curl http://localhost:8101/health    # M1 identity
curl http://localhost:8080/health    # M5 gateway
curl http://localhost:3000           # M6 UI

# 로그인 후 운영 가시성 확인
TOKEN=$(curl -sX POST http://localhost:8101/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<pw>"}' | jq -r .access_token)
make admin-health TOKEN=$TOKEN       # row counts + last sync 요약
```

### 3.7 Mock 모드 (DB/모델 없이)

```bash
make run-mock         # MODULE_IMPL=mock overlay, 인프라(PG/Redis)만 실제
```

---

## 4. 모듈별 운영

표준 ops 어휘는 모든 모듈에서 동일합니다:

```bash
cd modules/<module>          # 또는 루트에서 `make <op>-one m=<module>`
make help                    # 타깃 목록
make build / run / stop / remove / log
make test                    # 컨테이너 안에서 pytest 1회 실행
```

루트 vs 모듈 호출은 동일한 `docker compose` 명령을 생성하도록 보장됩니다 — 어느 쪽에서 실행하든 절대경로 기반의 같은 결과.

### 4.1 모듈별 추가 타깃

**M1 identity** — alembic + admin 운영
```bash
cd modules/m1-identity
make migrate                                   # alembic upgrade head (admin role 시드)
make create-admin EMAIL=... PASSWORD=...       # 신규 admin
make create-admin EMAIL=... PASSWORD=... OVERWRITE=1   # 비밀번호 회전
make admin-health TOKEN=<jwt>                  # row counts + last sync 요약
```

**M2 doc-to-md** — 문서 파이프라인
```bash
cd modules/m2-doc-to-md
make pipeline       # 컨테이너 안에서 1회 점진적 변환
```

**M3 chunk-embed** — pgvector 인덱스
```bash
cd modules/m3-chunk-embed
make migrate        # pgvector ext + chunks/documents 테이블
```

**M8 web-search** — 외부 검색 (CLI 직접 실행)
```bash
docker compose run --rm m8-web-search python -m app.cli search \
  --query "p53 phase 2 clinical trial" --provider curated
```

---

## 5. 개발 워크플로

### 5.1 사내 HR DB 동기화 (M1)

루트 `.env`에서:
- 필수: `MYSQL_URL`
- 선택 오버라이드: `MYSQL_TABLE_USERS` (기본 `USER_INFO`), `MYSQL_SYNC_INTERVAL_MINUTES` (기본 60), `MYSQL_SYNC_BATCH_SIZE` (기본 1000), `MYSQL_SYNC_ON_STARTUP` (기본 0)
- m1→m2 트리거: `M2_INTERNAL_SYNC_URL` + `INTERNAL_SYNC_TOKEN` (양쪽 일치 필수)

스키마 / 매핑 / SHA1 비밀번호 처리 등 상세는 [modules/m1-identity/README.md](modules/m1-identity/README.md).

### 5.2 사내 검색/HR DB → m2 (파일 메타 + 폴더 ACL)

루트 `.env`:
- `M2_MYSQL_FILE_URL` (검색 서버 `F0_00001_F`)
- `M2_MYSQL_HR_URL` (HR DB `PDiskFolderPermission2`)
- `M2_MYSQL_TABLE_FILES`, `M2_MYSQL_TABLE_FOLDER_PERMS` (기본값 = 사내 테이블명)

m1 성공 후 m1이 m2의 `/internal/sync/mysql`을 자동 호출. 상세는 [modules/m2-doc-to-md/README.md](modules/m2-doc-to-md/README.md).

### 5.3 Mock 토글로 부분 개발

```bash
make run-mock                                              # 전체 mock
docker compose -f infra/docker-compose.yml stop m3-chunk-embed
MODULE_IMPL=real docker compose -f infra/docker-compose.yml \
  up -d --no-deps m3-chunk-embed                           # m3만 real
```

### 5.4 Contract-first

- `packages/contracts/<m>.openapi.yaml`이 SSOT
- 모듈 구현이 lock된 SHA256과 일치하는지 CI가 검증

### 5.5 e2e 통합 테스트

```bash
python3 -m pytest tests-e2e/ -v --tb=short    # testcontainers (Docker 필요)
```

---

## 6. 관측성 / 백업

### 6.1 관측성 스택

```bash
make obs-up           # Prometheus + Grafana + Loki + Promtail + Alertmanager
make obs-down
```

| 서비스 | URL |
|--------|-----|
| Grafana | http://localhost:3002 (admin / `infra/secrets/grafana_password`) |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |

- 모든 백엔드 `/metrics` 노출 (M5는 Basic Auth 보호)
- 모듈 JSON 로그: 컨테이너 stdout (`make log`) + 호스트 `data/logs/<m>/<m>.log` (회전 10MB×5)
- 사전 정의 알림: `HighErrorRate`(>5%), `HighP99Latency`(>3s), `M1SyncFailure`, `DiskUsageHigh`, `CircuitBreakerOpen`

### 6.2 백업

```bash
make backup-pg        # pg_dump → backups/postgres_<ts>.sql.gz
make backup-neo4j     # neo4j-admin dump → backups/neo4j_<ts>.dump
make backup-all       # 둘 다
```

자동: `infra/cron/backup.sh`를 호스트 cron 등록 (retention은 스크립트 내부 정책).

---

## 7. 운영 환경 사양

| 항목 | 기준 |
|------|------|
| OS | Ubuntu 24.04 LTS |
| GPU | 1/4 NVIDIA (M3 임베딩 + M4 query embedding 공유) |
| RAM | 512 GB |
| 동시 사용자 | 100 |
| 분당 쿼리 | 200 qpm |
| PostgreSQL | pgvector/pgvector:pg16 (bind-mount → `${DATA_DIR}/postgres`) |
| Redis | 7 (appendonly, bind-mount → `${DATA_DIR}/redis`) |
| Neo4j | 5 (선택, Graph RAG용, bind-mount → `${DATA_DIR}/neo4j`) |

`DATA_DIR` / `LOG_DIR`은 Makefile이 절대경로로 export (기본 `<repo>/data/db`, `<repo>/data/logs`). 운영 서버에선 `DATA_DIR=/data/db make run` 식으로 오버라이드.

---

## 8. 디렉토리 구조

```
.
├── modules/                  # M1~M8 마이크로서비스 (각 Makefile + Dockerfile)
│   ├── m1-identity/          m2-doc-to-md/    m3-chunk-embed/    m4-rag/
│   ├── m5-gateway/           m6-ui/           m7-admin/{backend,frontend}/
│   └── m8-web-search/
├── packages/
│   ├── contracts/            # OpenAPI SSOT (7 YAML + .sha256 락)
│   └── shared-py/            # 공통 config / db / http / logging (rag_shared)
├── infra/
│   ├── docker-compose.{yml,base,mock,observability}.yml
│   └── secrets/  observability/  cron/
├── data/                     # bind-mount 영속 데이터 (gitignored)
│   ├── db/{postgres,neo4j,redis,m2-state}/
│   └── logs/<module>/
├── tests-e2e/                # testcontainers 통합 테스트
├── loadtest/                 # locust 시나리오
└── Makefile                  # docker-only 오케스트레이션 (build/run/stop/remove/log)
```

---

## 라이선스

(내부 배포용 — 라이선스 미정)
