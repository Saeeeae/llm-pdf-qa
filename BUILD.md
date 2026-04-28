# BUILD & RUN GUIDE

이 저장소는 8개 모듈로 구성된 RAG-LLM 모노레포입니다. **모든 모듈은 Docker로 빌드/배포**하며,
영속 데이터는 호스트의 두 경로에 바인드 마운트합니다.

```
DATA_ROOT  (default /data)  → DB, 모델 캐시, 마크다운, state, 로그
DATA2_ROOT (default /data2) → 원본 입력 문서 (read-only)
```

저장소 안에는 데이터를 두지 않습니다. 컨테이너만 ephemeral, 데이터는 호스트가 소유.

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
| `${DATA_ROOT}/logs/{m2,m5,m7,m8}` | `/data/logs`              | m2/m5/m7/m8      | RW    |
| `${DATA2_ROOT}`            | `/data2`                         | m2               | RO    |

### 1.2 저장소 (코드)

```
.
├── Makefile                     # 루트 오케스트레이션 (이 가이드의 진입점)
├── BUILD.md                     # ← 이 문서
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
# 1) 호스트 디렉토리 생성 (sudo 필요할 수 있음)
sudo make data-init                    # /data, /data2 하위 트리 생성
sudo chown -R $(id -u):$(id -g) /data /data2

# 2) Secrets 생성 (JWT, PG, Neo4j 비번)
make secrets-init

# 3) 빌드 + 기동 (data-init, secrets-init 포함)
make up

# 4) DB 스키마 (컨테이너 안에서 alembic 실행 — 호스트에 Python 없어도 됨)
make migrate                           # m1, m3 alembic upgrade head

# 5) 확인
make ps
curl -f http://localhost:8080/health   # m5-gateway
```

다른 경로를 쓰려면:
```bash
DATA_ROOT=/mnt/nvme/rag DATA2_ROOT=/mnt/nas/docs make up
```

### 3.2 Mock 모드 (DB/GPU 없이 UX 확인)

```bash
make up-mock     # 모든 모듈 MODULE_IMPL=mock
```

### 3.3 단일 모듈만

```bash
make up-one m=m3-chunk-embed   # base infra + m3만 띄움
make build-one m=m6-ui         # 이미지만 빌드
```

---

## 4. 자주 쓰는 명령

`make help`로 전체 목록을 볼 수 있습니다.

### 4.1 루트 Makefile

| 명령 | 동작 |
|------|------|
| `make data-init` | `${DATA_ROOT}` 하위 디렉토리 생성 |
| `make secrets-init` | `infra/secrets/{jwt,pg,neo4j}_secret` 자동 생성 |
| `make build-images` | 9개 서비스 이미지 전체 빌드 |
| `make build-one m=<svc>` | 특정 서비스만 빌드 (예: `m=m4-rag`) |
| `make build-no-cache` | `--no-cache` 전체 재빌드 |
| `make up` / `make up-mock` | real / mock 모드로 전체 기동 |
| `make up-one m=<dir>` | base infra + 단일 모듈 기동 |
| `make down` | 컨테이너 중지 (DATA_ROOT 보존) |
| `make down-clean` | 중지만 (수동 삭제 안내 출력) |
| `make ps` / `make logs s=<svc>` | 상태 / 로그 |
| `make restart s=<svc>` / `make shell s=<svc>` | 재시작 / 셸 |
| `make config` | 머지된 compose 출력 (디버깅) |
| `make migrate` / `migrate-down` / `migrate-status` | m1, m3 alembic — **컨테이너 안에서** `docker compose run --rm` 으로 실행 (호스트에 Python/alembic 불필요) |
| `make backup-all` | pg_dump + neo4j-admin dump → `backups/` |
| `make obs-up` / `obs-down` | Prometheus/Grafana 스택 |

### 4.2 모듈 Makefile (`cd modules/<m>`)

각 모듈은 동일한 인터페이스:

| 명령 | 동작 |
|------|------|
| `make help` | 타깃 목록 |
| `make install` | (호스트 venv용) 의존성 editable 설치 |
| `make run` / `make run-mock` | 호스트에서 직접 uvicorn (Docker 없이) |
| `make test` / `make test-cov` | 단위 테스트 |
| `make lint` / `make fmt` | ruff/eslint |
| `make build` (백엔드) / `make docker-build` (프론트엔드) | 컨테이너 이미지 빌드 |
| `make docker-up` | base infra + 이 모듈만 컨테이너로 기동 |
| `make docker-down` / `make docker-logs` | 정지 / 로그 |
| `make migrate` (m1, m3) | alembic |
| `make pipeline` (m2) | 문서→Markdown 1회 |

> `make build` (모듈)는 내부적으로 루트로 `cd`해서 `docker compose ... build`를 호출합니다.
> Dockerfile이 `packages/shared-py`를 필요로 하므로 컨텍스트가 항상 저장소 루트여야 합니다.

---

## 5. 환경 변수

### 5.1 호스트 경로

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATA_ROOT` | `/data` | DB/모델/마크다운/로그가 저장될 루트 |
| `DATA2_ROOT` | `/data2` | 원본 입력 문서 디렉토리 (RO) |

### 5.2 컨테이너 내부 (compose에서 자동 설정)

`infra/docker-compose.yml`이 모듈 서비스마다 다음을 강제합니다:

- m2: `M2_SOURCE_DIR=/data2`, `M2_OUTPUT_DIR=/data/markdown`, `M2_STATE_DIR=/data/state`, `M2_LOG_DIR=/data/logs`
- m3, m4: `HF_HOME=/data/models`, `TRANSFORMERS_CACHE=/data/models`, `SENTENCE_TRANSFORMERS_HOME=/data/models`
- m8: `M8_AUDIT_LOG=/data/logs/m8-web-search.jsonl`
- DB: `POSTGRES_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/ragdb` (Docker DNS)

`.env.example`은 컨테이너 기본값에 맞춰 작성되어 있어 `cp .env.example .env`만 하면 됩니다.

### 5.3 GPU 지정

```bash
NVIDIA_VISIBLE_DEVICES=2 make up    # m3, m4가 GPU 2번을 사용
```

---

## 6. CI/이미지 출시

```bash
make lint           # 전체 ruff/eslint
make test           # 백엔드 pytest
make test-fe        # 프론트 vitest
make test-e2e       # testcontainers
make security-scan  # bandit + safety + npm audit
make build-images   # 모든 이미지 빌드 (CI에서 GHCR push 전에 사용)
```

GitHub Actions:
- `.github/workflows/ci.yml` — lint + test + contracts-diff
- `.github/workflows/image-build.yml` — main 머지 시 변경된 모듈만 GHCR push
- `.github/workflows/pr-checks.yml` — schemathesis + 보안 스캔

---

## 7. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|-------------|
| `make up` 시 `mkdir: permission denied /data` | 호스트 권한. `sudo make data-init` 후 `chown` |
| 컨테이너가 모델을 매번 재다운로드 | `${DATA_ROOT}/models` 마운트 누락 또는 RO. `ls -la /data/models`, 권한 확인 |
| `m2-doc-to-md`가 입력을 못 찾음 | `${DATA2_ROOT}` 비어있거나 마운트 안됨. `docker exec m2-doc-to-md ls /data2` |
| 헬스체크 실패 (`curl: not found`) | 베이스 이미지 `python:3.11-slim`에 curl 없음. 모든 백엔드 Dockerfile이 `apt-get install curl`을 수행하므로 이미지 재빌드 필요: `make build-no-cache` |
| `network ragnet declared as external, but could not be found` | 모듈 compose만 단독으로 띄우려면 먼저 `docker network create ragnet` 또는 `make infra-up` |
| Next.js 번들의 API URL이 잘못됨 | `NEXT_PUBLIC_*`은 **빌드 시점에 박힘**. `NEXT_PUBLIC_API_BASE=... make build-one m=m6-ui` 후 재기동 |
| Postgres가 기존 데이터를 못 읽음 | `${DATA_ROOT}/db/postgres`의 PG 메이저 버전이 다른 경우. 백업 후 마이그레이션 필요 |

---

## 8. 변경 영향 (이번 리팩터링 요약)

- `infra/docker-compose.base.yml`: PG/Neo4j/Redis 모두 `${DATA_ROOT}`에 바인드 마운트
- `infra/docker-compose.yml`: 8개 모듈 모두 `${DATA_ROOT}` / `${DATA2_ROOT}` 마운트, env로 컨테이너 경로 강제
- 모든 백엔드 Dockerfile: `curl` 설치 (헬스체크용)
- m3, m4 Dockerfile: `HF_HOME` 등 모델 캐시 env 박음
- m6, m7-admin/frontend Dockerfile: `PORT`/`HOSTNAME` env, `NEXT_PUBLIC_*` build ARG
- m6-ui, m7-admin/frontend가 `infra/docker-compose.yml`의 include에 새로 추가
- 루트 `Makefile`: `data-init`, `secrets-init`, `build-one`, `restart`, `shell`, `config` 추가
- 모듈 `Makefile`: `build`가 compose 기반으로 변경 (저장소 루트 컨텍스트), `docker-up/down/logs` 추가
