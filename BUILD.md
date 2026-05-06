# BUILD & RUN GUIDE

이 저장소는 8개 모듈로 구성된 RAG-LLM 모노레포입니다. **모든 모듈은 Docker로 빌드/배포**하며,
영속 데이터는 호스트의 두 경로에 바인드 마운트합니다.

```
DATA_ROOT  (default /data)  → DB, 모델 캐시, 마크다운, state, 로그
DATA2_ROOT (default /data2) → 원본 입력 문서 (read-only)
```

저장소 안에는 데이터를 두지 않습니다. 컨테이너만 ephemeral, 데이터는 호스트가 소유.

> 운영 라이프사이클(첫 부팅 → 일상 운영 → 트러블슈팅) 풀가이드는 [docs/RUNBOOK.md](docs/RUNBOOK.md). 이 문서는 빌드/디렉토리/환경변수 기준.

---

## 1. 디렉토리 레이아웃

### 1.1 호스트 (DATA_ROOT)

| 호스트 경로                | 컨테이너 경로                    | 사용 모듈        | 종류  |
|----------------------------|----------------------------------|------------------|-------|
| `${DATA_ROOT}/db/postgres` | `/var/lib/postgresql/data`       | postgres         | RW    |
| `${DATA_ROOT}/db/neo4j`    | `/data`                          | neo4j            | RW    |
| `${DATA_ROOT}/db/redis`    | `/data`                          | redis            | RW    |
| `${DATA_ROOT}/models`      | `/data/models` (`HF_HOME`)       | m3, m4           | RW    |
| `${DATA_ROOT}/markdown`    | `/data/markdown`                 | m2 (W), m3 (R)   | RW/RO |
| `${DATA_ROOT}/state/m2`    | `/data/state`                    | m2               | RW    |
| `${DATA_ROOT}/logs/{m1,m2,m5,m7,m8}` | `/var/log/<m>`         | m1/m2/m5/m7/m8   | RW    |
| `${DATA2_ROOT}`            | `/data2`                         | m2               | RO    |

### 1.2 저장소 (코드)

```
.
├── Makefile                     # 루트 오케스트레이션 (이 가이드의 진입점)
├── BUILD.md                     # ← 이 문서 (빌드/디렉토리/환경변수)
├── docs/RUNBOOK.md              # 운영 라이프사이클 + 검증 + 트러블슈팅
├── README.md                    # 프로젝트 전체 개요
├── infra/
│   ├── docker-compose.yml       # 8개 모듈 + base를 합쳐 부르는 메인 compose
│   ├── docker-compose.base.yml  # postgres, neo4j, redis (DATA_ROOT 마운트)
│   ├── docker-compose.mock.yml  # 모든 모듈을 mock 모드로 띄움
│   ├── docker-compose.observability.yml  # Prometheus/Grafana/Loki
│   └── secrets/                 # JWT/PG/Neo4j 비밀 (Docker secrets로 주입)
├── modules/
│   ├── m1-identity/             # 각 모듈은 Dockerfile + docker-compose.module.yml + Makefile 보유
│   ├── m2-doc-to-md/
│   ├── m3-chunk-embed/
│   ├── m4-rag/
│   ├── m5-gateway/
│   ├── m6-ui/                   # Next.js (standalone), 빌드 컨텍스트 = 모듈 dir
│   ├── m7-admin/{backend,frontend}/
│   └── m8-web-search/
└── packages/
    ├── shared-py/               # 백엔드 공통 라이브러리 (모든 백엔드 Dockerfile이 COPY)
    └── contracts/               # OpenAPI SSOT
```

---

## 2. 빌드 전략

### 2.1 빌드 단위

| 단위 | 산출물 | 정의 위치 |
|------|--------|-----------|
| 백엔드 모듈 (m1, m2, m3, m4, m5, m7-admin/backend, m8) | `python:3.11-slim` 기반 이미지 | 모듈의 `Dockerfile` |
| 프론트엔드 (m6-ui, m7-admin/frontend) | `node:20-alpine` 기반 standalone Next.js 이미지 | 모듈의 `Dockerfile` |
| 인프라 (postgres, neo4j, redis) | 외부 이미지 (빌드 없음) | `infra/docker-compose.base.yml` |

### 2.2 빌드 컨텍스트가 다른 이유

- **백엔드**: Dockerfile이 `./packages/shared-py`와 `./modules/<m>`를 모두 COPY하므로
  **빌드 컨텍스트는 저장소 루트**여야 합니다. 모듈 compose는 `context: ../..` (m7은 `../../..`)로 설정.
- **프론트엔드**: standalone Next.js라 자기 디렉토리만 필요. 컨텍스트는 `.` (모듈 dir).
- **모델 캐시**: Dockerfile에 `HF_HOME=/data/models` 환경변수만 박아두고,
  실제 캐시는 `${DATA_ROOT}/models`에서 마운트. 이미지에 모델을 굽지 않습니다.

### 2.3 NEXT_PUBLIC_* (빌드 시 박는 값)

Next.js의 `NEXT_PUBLIC_*` 변수는 빌드 시점에 JS 번들에 박히므로 런타임에는 못 바꿉니다.
모듈 `docker-compose.module.yml`이 `args:`로 build에 전달:

```yaml
build:
  args:
    NEXT_PUBLIC_API_BASE: ${NEXT_PUBLIC_API_BASE:-http://m5-gateway:8000}
```

오버라이드:
```bash
NEXT_PUBLIC_API_BASE=https://rag.corp.local make build-one m=m6-ui
```

---

## 3. 빠른 시작

### 3.1 첫 부팅 (전체 스택)

```bash
# 1) 호스트 디렉토리 + 권한 (data/db, data/logs 자동 생성, chmod 777)
make prepare

# 2) Secrets 생성 (JWT, PG, Neo4j 비번)
mkdir -p infra/secrets
for n in jwt_secret postgres_password neo4j_password grafana_password; do
  openssl rand -base64 48 > infra/secrets/$n
  chmod 600 infra/secrets/$n
done

# 3) .env (SSOT) 작성
cp .env.example .env
# 필수: POSTGRES_PASSWORD, NEO4J_PASSWORD, JWT_SECRET (32자+),
#       INTERNAL_SYNC_TOKEN, MYSQL_URL, M2_MYSQL_FILE_URL
# 선택: BOOTSTRAP_ADMIN_EMAIL/PASSWORD (첫 admin 자동 생성)

# 4) 빌드 + 마이그레이션 + 기동
make build
make migrate          # m1, m3 alembic upgrade head (admin role 시드 포함)
make run              # prepare를 자동 의존

# 5) 확인
make ps
curl -f http://localhost:8101/health   # m1-identity
curl -f http://localhost:8080/health   # m5-gateway
```

다른 호스트 데이터 경로를 쓰려면:
```bash
DATA_DIR=/mnt/nvme/rag/db LOG_DIR=/mnt/nvme/rag/logs make run
```

### 3.2 Mock 모드 (DB/GPU 없이 UX 확인)

```bash
make run-mock     # 모든 모듈 MODULE_IMPL=mock
```

### 3.3 단일 모듈만

```bash
make run-one m=m3-chunk-embed   # base infra + m3만 기동
make build-one m=m6-ui          # 이미지만 빌드
make log-one m=m1-identity      # 로그 follow
make stop-one m=m1-identity     # 정지
```

---

## 4. 자주 쓰는 명령

`make help`로 전체 목록을 볼 수 있습니다. 표준 ops 어휘는 `build / run / stop / remove / log` 5개로 통일.

### 4.1 루트 Makefile

| 명령 | 동작 |
|------|------|
| `make prepare` | `${DATA_DIR}/{postgres,neo4j,redis,m2-state}` + `${LOG_DIR}/<m>` 생성, perm 777 |
| `make build` | 모든 모듈 이미지 빌드 |
| `make build-one m=<svc>` | 특정 서비스만 빌드 (예: `m=m4-rag`) |
| `make run` / `make run-mock` | real / mock 모드로 전체 기동 (`prepare` 자동 의존) |
| `make run-one m=<dir>` | base infra + 단일 모듈 기동 |
| `make stop` / `make stop-one m=<dir>` | 컨테이너 중지 (호스트 데이터 보존) |
| `make remove` / `make remove-one m=<dir>` | 컨테이너 + 도커 볼륨 제거 (호스트 bind는 유지) |
| `make log s=<svc>` / `make log-one m=<dir>` | 로그 follow |
| `make ps` | 상태 |
| `make infra-up` / `make infra-down` | postgres + neo4j + redis만 |
| `make migrate` | m1, m3 alembic — **컨테이너 안에서** `docker compose run --rm` 실행 (호스트 Python/alembic 불필요) |
| `make backup-pg` / `make backup-neo4j` / `make backup-all` | `backups/` 로 dump |
| `make obs-up` / `make obs-down` | Prometheus/Grafana/Loki 스택 |

### 4.2 모듈 Makefile (`cd modules/<m>`)

각 모듈은 동일한 인터페이스 (루트와 같은 어휘, docker compose wrapper):

| 명령 | 동작 |
|------|------|
| `make help` | 타깃 목록 |
| `make build` | 이 모듈 이미지 빌드 (저장소 루트 컨텍스트) |
| `make run` | base infra + 이 모듈만 기동 |
| `make stop` | 정지 (도커 볼륨 보존) |
| `make remove` | 정지 + 도커 볼륨 제거 |
| `make log` | 이 모듈 로그 follow |
| `make test` | 컨테이너 안에서 pytest 1회 실행 |
| `make migrate` (m1, m3) | alembic upgrade head |
| `make pipeline` (m2) | 문서→Markdown 1회 |
| `make create-admin` (m1) | `EMAIL=… PASSWORD=… [OVERWRITE=1]` admin 생성/회전 |
| `make admin-health` (m1) | `TOKEN=<jwt>` 로 /admin/health 조회 |

> 모듈 Makefile은 내부적으로 `docker compose -f infra/docker-compose.base.yml -f modules/<m>/docker-compose.module.yml`을 호출합니다. 루트에서 실행하든 모듈 디렉토리에서 실행하든 동일한 명령을 생성합니다 (`${ROOT}` env export로 절대경로 보장).

---

## 5. 환경 변수

### 5.1 호스트 경로

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATA_DIR` | `<repo>/data/db` | DB 영속 (postgres/neo4j/redis/m2-state) |
| `LOG_DIR` | `<repo>/data/logs` | 모듈별 JSON 로그 (회전 10MB × 5) |
| `DATA2_ROOT` | `/data2` | 원본 입력 문서 디렉토리 (RO, m2가 사용) |

운영 서버에선:
```bash
DATA_DIR=/mnt/nvme/rag/db LOG_DIR=/mnt/nvme/rag/logs DATA2_ROOT=/mnt/nas/docs make run
```

### 5.2 컨테이너 내부 (compose에서 자동 설정)

`infra/docker-compose.yml`이 모듈 서비스마다 다음을 강제합니다:

- m2: `M2_SOURCE_DIR=/data2`, `M2_OUTPUT_DIR=/data/markdown`, `M2_STATE_DIR=/app/.state`, `LOG_FILE_PATH=/var/log/m2-doc-to-md/m2-doc-to-md.log`
- m3, m4: `HF_HOME=/data/models`, `TRANSFORMERS_CACHE=/data/models`, `SENTENCE_TRANSFORMERS_HOME=/data/models`
- m1: `LOG_FILE_PATH=/var/log/m1-identity/m1-identity.log`
- m8: `M8_AUDIT_LOG=/var/log/rag-audit/m8-web-search.jsonl`
- DB: `POSTGRES_URL=postgresql+psycopg://postgres:postgres@postgres:5432/ragdb` (Docker DNS)

루트 `.env`가 SSOT — 모듈 compose의 `env_file: ${ROOT}/.env`로 모든 변수를 컨테이너에 전달합니다. 모듈 `.env.example`은 stub (사용 변수 목록 문서) 역할만 합니다.

### 5.3 GPU 지정

```bash
NVIDIA_VISIBLE_DEVICES=2 make run    # m3, m4가 GPU 2번을 사용
```

---

## 6. CI / 이미지 출시

GitHub Actions:
- `.github/workflows/ci.yml` — lint + test + contracts-diff
- `.github/workflows/image-build.yml` — main 머지 시 변경된 모듈만 GHCR push
- `.github/workflows/pr-checks.yml` — schemathesis + 보안 스캔

수동 빌드는 `make build` (전체) 또는 `make build-one m=<svc>` (단일).

---

## 7. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|-------------|
| `make run` 시 `mkdir: permission denied` | 호스트 권한. `make prepare`가 `chmod 777`까지 자동, 그래도 막히면 `sudo chown -R 999:999 data/db/postgres` (postgres 컨테이너 uid) |
| 컨테이너가 모델을 매번 재다운로드 | `${DATA_DIR}/../models` 마운트 누락 또는 RO. `ls -la <DATA_ROOT>/models` 권한 확인 |
| `m2-doc-to-md`가 입력을 못 찾음 | `${DATA2_ROOT}` 비어있거나 마운트 안됨. `docker exec m2-doc-to-md ls /data2` |
| 헬스체크 실패 (`curl: not found`) | 베이스 이미지 `python:3.11-slim`에 curl 없음. 모든 백엔드 Dockerfile이 `apt-get install curl`을 수행하므로 이미지 재빌드 필요. `docker compose build --no-cache` |
| `network ragnet declared as external, but could not be found` | 모듈 compose만 단독으로 띄우려면 먼저 `docker network create ragnet` 또는 `make infra-up` |
| Next.js 번들의 API URL이 잘못됨 | `NEXT_PUBLIC_*`은 **빌드 시점에 박힘**. `NEXT_PUBLIC_API_BASE=... make build-one m=m6-ui` 후 재기동 |
| Postgres가 기존 데이터를 못 읽음 | `${DATA_DIR}/postgres`의 PG 메이저 버전이 다른 경우. 백업 후 마이그레이션 필요 |
| m1 부팅 시 `admin role not found` | `make migrate` 미실행. alembic 0001이 admin 시드를 만듭니다 |
| m1→m2 트리거가 401 | `INTERNAL_SYNC_TOKEN` 양쪽 .env에서 동일하게 설정 (m1 측이 fail-fast 로그 emit) |

---

## 8. 변경 영향 (리팩터링 요약)

### 8.1 1차 (PR #1, Docker-first refactor)

- `infra/docker-compose.base.yml`: PG/Neo4j/Redis 모두 호스트 바인드 마운트
- 모든 백엔드 Dockerfile: `curl` 설치 (헬스체크용)
- m3, m4 Dockerfile: `HF_HOME` 등 모델 캐시 env 박음
- m6, m7-admin/frontend Dockerfile: `PORT`/`HOSTNAME` env, `NEXT_PUBLIC_*` build ARG
- m6-ui, m7-admin/frontend가 `infra/docker-compose.yml`의 include에 추가
- m1 alembic 0003 down_revision 오타 수정 (`KeyError` 픽스)
- m1 SQL identifier validation (env-var-controlled table names)

### 8.2 2차 (m1↔m2 ordered sync + admin bootstrap + ops 어휘 통일)

- m1↔m2 sync ordering: `INTERNAL_SYNC_TOKEN` + `M2_INTERNAL_SYNC_URL`로 m1 성공 후 자동 m2 트리거
- m1 사내 USER_INFO 스키마 매핑 (POS/DEPT distinct 도출, SHA1 비밀번호 자동 argon2 회전)
- m1 admin bootstrap: `BOOTSTRAP_ADMIN_*` env로 첫 admin 자동 생성, `make create-admin` CLI
- m1 `GET /admin/health`: row counts + last sync 요약 (RBAC: admin.read)
- 파일 로깅 (m1, m2): `LOG_FILE_PATH` 환경변수, 회전 10MB×5
- Makefile 어휘 통일: `up/down/build-images/...` → `build / run / stop / remove / log`
- 루트 `.env` SSOT 통합: 모듈 `.env.example`은 stub
- POSTGRES URL 분리: `POSTGRES_URL` (psycopg, sync) + `POSTGRES_ASYNC_URL` (asyncpg) + `POSTGRES_RO_URL`
