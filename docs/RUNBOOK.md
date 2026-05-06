# RUNBOOK — 운영 순서와 검증

루트 Makefile은 모든 운영 명령을 `build / run / stop / remove / log` 5개 동사로 통일합니다. 이 문서는 처음 배포부터 일상 운영까지의 **순서**와 **각 단계의 검증 방법**을 정리합니다.

## 0. 변수 한눈에

| 변수 | 의미 | 누가 설정 |
|---|---|---|
| `ROOT` | 모노레포 절대경로 | Makefile이 `git rev-parse`로 자동 |
| `DATA_DIR` | DB bind-mount 호스트 경로 | Makefile 기본 `${ROOT}/data/db`, 운영서버는 `/data/db` 등으로 override |
| `LOG_DIR` | 로그 bind-mount 호스트 경로 | Makefile 기본 `${ROOT}/data/logs` |
| `INTERNAL_SYNC_TOKEN` | m1↔m2 공유 시크릿 | 운영자가 `.env`에 설정 (필수) |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | 첫 부팅 시 admin 자동 생성 | 운영자가 `.env`에 설정 (선택) |

---

## 1. 최초 배포 — 처음 한 번만

```bash
# 1-1. 저장소 + 의존 환경
git clone <repo> && cd llm_again
docker --version           # 24.0+
docker compose version     # v2

# 1-2. 시크릿 (JWT/PG/Neo4j/Grafana 비밀번호 파일)
mkdir -p infra/secrets
for n in jwt_secret postgres_password neo4j_password grafana_password; do
  openssl rand -base64 48 > infra/secrets/$n
  chmod 600 infra/secrets/$n
done

# 1-3. .env 작성 (SSOT)
cp .env.example .env
# 필수 채워야 할 키:
#   POSTGRES_PASSWORD       (위에서 생성한 secret 값과 동일하게)
#   NEO4J_PASSWORD          (동상)
#   JWT_SECRET              (32자 이상)
#   INTERNAL_SYNC_TOKEN     (m1↔m2 공유, 임의 random)
#   MYSQL_URL               (사내 HR DB)
#   M2_MYSQL_FILE_URL       (사내 검색 DB)
#   M2_MYSQL_HR_URL         (사내 HR DB, MYSQL_URL과 같은 서버여도 무관)
# 권장:
#   BOOTSTRAP_ADMIN_EMAIL=admin@example.com
#   BOOTSTRAP_ADMIN_PASSWORD='<32+chars>'

# 1-4. 호스트 디렉토리 + 권한
make prepare
# → data/db/{postgres,neo4j,redis,m2-state} 생성, perm 777
# → data/logs/<m>/ 모듈별 디렉토리 생성

# 1-5. 모든 이미지 빌드
make build

# 1-6. DB 스키마 (alembic) — 첫 run 직전에 1회
make migrate
# → m1-identity 0001/0002/0003 적용 (admin/manager/user role 시드 포함)
# → m3-chunk-embed pgvector 확장 + chunks/documents 테이블

# 1-7. 전체 스택 기동
make run
# → make prepare가 의존으로 자동 실행됨 (멱등)
# → 컨테이너가 background에서 떠오름

# 1-8. 검증
make ps
# → 모든 서비스가 healthy 상태인지 확인 (postgres/redis/neo4j는 healthcheck 통과 후 m1 등이 시작)
```

### 1-9. 부팅 검증 체크리스트

```bash
# 헬스 — 각 모듈
curl -s http://localhost:8101/health | jq    # m1 identity
curl -s http://localhost:8102/health | jq    # m2 doc-to-md
curl -s http://localhost:8103/health | jq    # m3 chunk-embed
curl -s http://localhost:8104/health | jq    # m4 rag
curl -s http://localhost:8080/health | jq    # m5 gateway
curl -s http://localhost:8107/health | jq    # m7 admin
curl -s http://localhost:8108/health | jq    # m8 web search

# 의존 readiness — m1은 PG+Redis까지 점검
curl -s http://localhost:8101/ready | jq
# 정상: {"status": "ok"}
# 비정상: {"status": "degraded", "errors": ["db: ...", "redis: ..."]}

# admin 자동 생성 확인 — BOOTSTRAP_ADMIN_*을 넣었다면
make log-one m=m1-identity | grep -i bootstrap
# 정상 케이스 로그 예: "Bootstrap created admin admin@example.com"
# 또는: "Bootstrap skipped — N admin(s) already exist"
# 또는: "Bootstrap skipped — BOOTSTRAP_ADMIN_EMAIL/PASSWORD not set"
```

### 1-10. (BOOTSTRAP_ADMIN_* 미설정 시) admin 수동 생성

```bash
cd modules/m1-identity
make create-admin EMAIL=admin@example.com PASSWORD='<32+chars>'
# → "ok: id=1 email=admin@example.com role_id=1"
```

비밀번호 회전이 필요할 땐 `OVERWRITE=1` 추가.

### 1-11. 첫 로그인 → admin/health 확인

```bash
TOKEN=$(curl -sX POST http://localhost:8101/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<password>"}' \
  | jq -r .access_token)

# 운영 가시성: row counts + last sync 요약
curl -s http://localhost:8101/admin/health -H "Authorization: Bearer $TOKEN" | jq
# 또는: cd modules/m1-identity && make admin-health TOKEN=$TOKEN
```

기대 응답:
```json
{
  "users": {"total": 1, "active": 1, "by_role": {"admin": 1}},
  "roles": {"total": 3},
  "departments": {"total": 0},
  "last_sync_run": null
}
```

`last_sync_run`은 첫 MySQL 동기화 후 채워짐.

---

## 2. 일상 운영 명령어

| 작업 | 전체 스택 | 단일 모듈 |
|---|---|---|
| 빌드 (Dockerfile/코드 변경 후) | `make build` | `make build-one m=m1-identity` |
| 시작 | `make run` | `make run-one m=m1-identity` |
| 정지 (데이터 유지) | `make stop` | `make stop-one m=m1-identity` |
| 컨테이너 + 도커 볼륨 제거 (호스트 bind 데이터는 유지) | `make remove` | `make remove-one m=m1-identity` |
| 로그 follow | `make log s=m1-identity` | `make log-one m=m1-identity` |
| 상태 | `make ps` | — |
| 인프라만 | `make infra-up` / `make infra-down` | — |

### 2-1. 코드 변경 → 재배포 사이클

```bash
# Python/요구사항 변경
cd modules/m1-identity
make build              # 새 이미지 빌드
make stop && make run   # 또는 그냥 `make run` (compose가 변경 감지하고 재생성)
make log                # 부팅 로그 확인
```

### 2-2. 모듈 하나만 mock으로 띄우기

```bash
# 전체는 real, m3만 mock
make run
docker compose -f infra/docker-compose.yml stop m3-chunk-embed
MODULE_IMPL=mock docker compose -f infra/docker-compose.yml \
  -f infra/docker-compose.mock.yml up -d --no-deps m3-chunk-embed
```

### 2-3. 사내 DB 동기화 수동 실행

```bash
# m1 (admin RBAC 필요)
curl -X POST http://localhost:8101/admin/sync/mysql \
  -H "Authorization: Bearer $TOKEN"

# m2 (token-gated)
curl -X POST http://localhost:8102/internal/sync/mysql \
  -H "X-Internal-Token: $INTERNAL_SYNC_TOKEN"

# 결과 확인
curl -s http://localhost:8101/admin/sync/mysql/status \
  -H "Authorization: Bearer $TOKEN" | jq .last_run
curl -s http://localhost:8102/internal/sync/mysql/status \
  -H "X-Internal-Token: $INTERNAL_SYNC_TOKEN" | jq .last_run
```

m1 성공 시 자동으로 m2가 트리거됨 — 위는 둘 다 강제 호출이 필요할 때 사용.

---

## 3. 로그와 데이터의 위치

### 3-1. 로그
| 어디서 | 어떻게 |
|---|---|
| 컨테이너 stdout (실시간) | `make log s=m1-identity` 또는 `docker compose ... logs -f` |
| 호스트 영속 (JSON) | `data/logs/<module>/<module>.log` (10MB × 5 회전) |
| 관측성 스택 | `make obs-up` 후 Grafana → Loki 데이터소스 |

### 3-2. 데이터
| 무엇 | 어디 (호스트) | 컨테이너 마운트 |
|---|---|---|
| Postgres | `data/db/postgres/` | `/var/lib/postgresql/data` |
| Neo4j | `data/db/neo4j/` | `/data` (in neo4j) |
| Redis | `data/db/redis/` | `/data` (in redis) |
| m2 sync state | `data/db/m2-state/sync_state.json` | `/app/.state/` |
| m1 audit | Postgres `audit_log` 테이블 | — |
| m8 audit | `data/logs/m8-web-search/audit.jsonl` | `/var/log/rag-audit/` |

`make remove`는 컨테이너만 지우고 호스트 bind는 유지. 진짜 초기화는 `rm -rf data/`.

---

## 4. 백업 / 복원

```bash
make backup-pg          # data/postgres dump → backups/postgres_<ts>.sql.gz
make backup-neo4j       # neo4j dump → backups/neo4j_<ts>.dump
make backup-all

# 복원 (Postgres 예)
zcat backups/postgres_<ts>.sql.gz | docker compose exec -T postgres \
  psql -U $POSTGRES_USER $POSTGRES_DB
```

---

## 5. 트러블슈팅

### 5-1. `make run` 후 m1이 unhealthy

```bash
make log-one m=m1-identity | tail -30
```
흔한 원인:
- `JWT_SECRET must be set (>=32 chars)` → `.env`의 JWT_SECRET 확인
- `admin role not found — run migrations first` → `make migrate` 미실행
- DB 연결 실패 → `make ps`로 postgres가 healthy인지, `POSTGRES_URL` 호스트가 `postgres`인지 (localhost가 아니어야 함)

### 5-2. m1→m2 트리거가 401

m1 로그에서 `INTERNAL_SYNC_TOKEN is empty — m2 trigger will be rejected (401)` 발견 시 `.env`의 `INTERNAL_SYNC_TOKEN`을 양쪽에서 동일하게 설정. (Phase 1-3 작업으로 m1 측은 fail-fast 로그를 emit합니다.)

### 5-3. Permission Denied (호스트 bind dir)

postgres 컨테이너가 uid 999. 호스트 디렉토리 소유주가 사용자라면 권한 문제. `make prepare`가 `chmod 777`까지 해주는데 그래도 막히면:
```bash
sudo chown -R 999:999 data/db/postgres
sudo chown -R 7474:7474 data/db/neo4j
```

### 5-4. 로그 파일이 안 생김

`LOG_FILE_PATH` 환경변수가 모듈 compose에 설정되어 있는지 확인. m1만 현재 적용되어 있고, m2도 Phase 3 후속에서 설정됨. 다른 모듈은 stdout만 사용. fail-fast가 필요하면 `LOG_FILE_REQUIRED=1` 추가.

### 5-5. 멀티 워커로 늘리고 싶은데?

m1 Dockerfile은 `--workers 1`로 고정. `RotatingFileHandler`는 multi-process 안전하지 않아 회전 시 데이터 손실. 수평 확장이 필요하면:
- 같은 모듈을 docker compose `replicas`로 늘려 컨테이너 수를 늘리거나,
- `concurrent_log_handler.ConcurrentRotatingFileHandler`로 swap (별도 의존)

---

## 6. 한 줄 요약

```
# 처음:    prepare → build → migrate → run → (admin) → admin-health
# 일상:    log / stop / run / build → run
# 정리:    stop (데이터 유지) / remove (도커 볼륨만 정리) / rm -rf data/ (초기화)
```
