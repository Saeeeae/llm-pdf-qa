# RAG-LLM Monorepo — Phase Progress

## Phase B2 — M3/M4 정합성 강화 (2026-04-27)

### B2.1 M3 동시성 + Idempotency
- `modules/m3-chunk-embed/app/routers/chunk_embed.py`: `_SEM = asyncio.Semaphore(int(os.getenv("M3_MAX_CONCURRENT","2")))` — `_run` 전체를 `async with _SEM:` 보호
- Idempotency: `X-Idempotency-Key` 헤더 또는 `doc_id+source_hash` body 조합 → Redis `m3:idem:{key}` SET NX EX 86400; 중복 시 `{"status":"duplicate"}` 즉시 반환
- Redis 불가 시 graceful fallback (항상 queued 진행)
- `_run` 실패 시 `m3_status='error'` + `error_msg` 저장; `m3_started_at` 타임스탬프 기록

### B2.2 M3 batch_size 동적
- `modules/m3-chunk-embed/app/embedder.py`: `_safe_batch_size(default=32)` — GPU free 메모리 < 4 GB이면 `max(8, default//2)` 반환
- `encode(texts, batch_size=None)` — None이면 `_safe_batch_size()` 자동 사용

### B2.3 M4 Hybrid 가중치 환경변수
- `modules/m4-rag/app/retriever.py`: `RRF_K=int(os.getenv("RRF_K","60"))`, `VEC_WEIGHT`, `BM25_WEIGHT` 환경변수화
- 융합: `weight / (RRF_K + rank)` 사용

### B2.4 M4 Redis 세션 히스토리
- 신규 파일: `modules/m4-rag/app/session.py` — `get_history()` / `add_turn()` (lpush + ltrim + expire, TTL 3600s, MAX_TURNS=5)
- `modules/m4-rag/app/routers/rag.py`: body에 `session_id` 필드; non-stream 응답 후 `add_turn`, stream 모드에서 토큰 누적 후 `add_turn`

### B2.5 M4 vLLM 회로차단기
- `modules/m4-rag/app/llm_client.py`: `CB` 클래스 (threshold=5, recovery=30s); `_cb` 전역 인스턴스
- `generate_stream` 진입 시 `can_call()` 검사; 성공/실패 시 `record()` 호출

### Alembic 마이그레이션
- 신규 파일: `modules/m3-chunk-embed/alembic/versions/0002_add_error_msg.py` — `error_msg TEXT`, `m3_started_at TIMESTAMP` 컬럼 추가 (down_revision=0001)

### 의존성
- m3 `pyproject.toml`: `redis>=5.0` 추가
- m4 `pyproject.toml`: `redis>=5.0` 추가

### 테스트 결과
- m3: 18 → **28** passed (`test_concurrency.py` +4, `test_idempotency.py` +6, `test_pipeline.py` 1개 동작 변경 반영)
- m4: 24 → **41** passed (`test_session.py` +5, `test_circuit.py` +7, `test_retriever_weights.py` +5)

---

## Phase B5 — Infra Hardening (2026-04-27)

### B5.1 Healthcheck + depends_on
- `infra/docker-compose.base.yml`: all three infra services now have healthchecks
  - postgres (`pgvector/pgvector:pg16`): `pg_isready` probe, interval 10s, start_period 20s
  - neo4j: `wget -O-` probe, interval 15s, start_period 30s
  - redis (`appendonly yes`): `redis-cli ping`, interval 10s
- `infra/docker-compose.yml`: all module services (m1, m2, m3, m4, m5, m7-admin, m8) have
  `depends_on` with `condition: service_healthy` on postgres/redis and `/ready` healthchecks

### B5.2 Docker Secrets
- `infra/docker-compose.yml`: `secrets:` top-level block with `jwt_secret`, `postgres_password`, `neo4j_password`
- Services with secret bindings: m1 (jwt+pg), m5 (jwt), m7-admin (jwt+pg), plus `_FILE` env vars
- `packages/shared-py/rag_shared/secrets.py`: `from_env_or_file()` helper — reads plain env or `NAME_FILE`
- `infra/secrets/.gitignore`: blocks all secret files, allows `.example`
- `infra/secrets/*.example`: placeholder files for jwt, postgres, neo4j
- `.env.example`: passwords/JWT changed to empty string with `# REQUIRED` annotations and `_FILE` examples

### B5.3 Backup Automation
- `Makefile`: `backup-pg`, `backup-neo4j`, `backup-all`, `restore-pg` targets added
- `infra/cron/backup.sh`: daily backup script + 30-day local retention pruning (chmod +x)

### B5.4 GPU Distribution
- `infra/docker-compose.yml` m3-chunk-embed: `deploy.resources.reservations.devices` (nvidia, count 1, gpu) + `CUDA_VISIBLE_DEVICES=0`
- m4-rag: same GPU allocation (shares GPU 0 with m3; vLLM is a separate server)

### B5.5 Audit Log Centralisation
- m8-web-search service: `volumes: [audit_logs:/var/log/rag-audit]`, `M8_AUDIT_LOG=/var/log/rag-audit/m8-web-search.jsonl`
- `volumes: audit_logs: {driver: local}` defined in docker-compose.yml
- `infra/logrotate.d/rag-audit`: daily rotation, 90-day retention, compress + delaycompress + copytruncate

### Skipped / Host-dependent
- Cron registration (`crontab -e`) — host environment dependent; script in `infra/cron/backup.sh` ready
- `logrotate` install — host package; config in `infra/logrotate.d/rag-audit` ready for `sudo cp`
- `docker compose config` full validation — requires Docker daemon and real secret files (sandbox has no Docker)
- YAML syntax validated via `python3 yaml.safe_load` — all files pass

---

## Phase B3 — E2E 통합 테스트 + Schemathesis Contract Lock (2026-04-27)

### B3.1 E2E 통합 테스트 (testcontainers)

신규 디렉토리: `tests-e2e/`

- `tests-e2e/conftest.py`:
  - `infra_containers` (session-scoped): testcontainers로 `pgvector/pgvector:pg16` + `redis:7` 기동; Docker 없으면 자동 skip
  - `m1_client` ~ `m5_client`: 각 모듈 FastAPI 앱을 ASGI transport (in-process)로 구동
  - M3 embedder monkeypatch: zero vector dim=1024 (`_FakeModel`)
  - M4 vLLM monkeypatch: echo stub (`_fake_generate`)
- `tests-e2e/test_chain.py` (3 tests):
  - `test_full_chain`: M2 `/ingest/scan` → M3 `/chunk-embed` → M4 `/rag/query` 체인 검증
  - `test_doc_delete_cascade`: `@pytest.mark.xfail` + TODO 주석 (cascade delete 미구현)
  - `test_idempotency_chain`: 동일 doc_id 2회 처리 → chunk 중복 없음 검증
- `tests-e2e/test_auth_chain.py` (4 tests):
  - `test_jwt_issue_and_gateway_pass`: M1 JWT 발급 → M5 통과
  - `test_expired_token_rejected`: 만료 토큰 → 401
  - `test_refresh_rotation`: refresh rotation 검증 (old token 재사용 거부)
  - `test_no_token_rejected`: 토큰 없음 → 401/403
- `tests-e2e/pyproject.toml`: `e2e` extras (testcontainers, psycopg[binary], httpx, PyJWT)
- **collect 결과**: 7 tests collected (import-only; sandbox Docker 없어 실행은 skip)

### B3.2 Schemathesis Contract Lock

각 모듈에 `tests/test_contract.py` 추가 (정적 스펙 검증, 라이브 서버 불요):

| 모듈 | 클래스 | collect |
|------|--------|---------|
| m1-identity | TestM1Contract | 3 |
| m2-doc-to-md | TestM2IngestContract | 3 |
| m3-chunk-embed | TestM3ChunkEmbedContract | 3 |
| m4-rag | TestM4RagContract | 3 |
| m5-gateway | TestM5GatewayContract | 3 |
| m7-admin/backend | TestM7AdminContract | 3 |
| m8-web-search | TestM8WebSearchContract | 3 |

테스트 3종: `test_spec_loads_without_error` / `test_all_operations_have_responses` / `test_request_generation`
schemathesis 미설치 환경에서는 `pytest.mark.skipif`로 자동 skip (import 오류 없음 확인).

Baseline lock:
- `packages/contracts/.lock/` — 7개 `.sha256` 파일 생성
- `scripts/contracts-lock.sh` / `scripts/contracts-verify.sh` (chmod +x)
- `bash scripts/contracts-verify.sh` → **7/7 OK**

### B3.3 통합 Makefile 타깃

- `test-e2e`: `python -m pytest tests-e2e/ -v --tb=short`
- `contracts-lock`: SHA256 baseline 갱신
- `contracts-verify`: drift 감지 (CI 실패 처리)
- `test-all`: `make test && make test-e2e`

`.github/workflows/ci.yml` `contracts-diff` 잡에 `contracts-verify` step 추가.

### Skipped / 제약
- E2E 실제 실행: sandbox Docker 없음 → `infra_containers` fixture가 `pytest.skip` 호출 (코드 + collect 검증만 수행)
- Schemathesis 실행: 패키지 미설치 → `skipif` 처리
- `test_doc_delete_cascade`: `xfail` 마킹 (cascade delete 미구현 — issue TODO 주석 포함)
- M7-admin contract test는 `pathlib.parents[5]`로 contracts 경로 지정 (모듈 depth 차이)

---

## Phase B6 — Load Testing & Observability (2026-04-27)

### B6.1 Locust Load Scenarios
- `loadtest/locustfile.py`: `RagUser` (7:2:1 task mix — POST /chat, GET /users, GET /health); `LOAD_JWT` env var; `between(1,3)` wait
- `loadtest/scenarios/spike.py`: `SpikeShape` — 0→200 users over 30 s, hold 120 s, ramp down 30 s
- `loadtest/scenarios/sustained.py`: `SustainedShape` — 100 users, rate 10/s, 30 minutes (`-u 100 -r 10 -t 30m` equivalent)
- `loadtest/analyze.py`: reads `*_stats.csv` + `*_stats_history.csv`, prints summary table, saves `*_latency.png` (p50/p95, English labels)
- `loadtest/README.md`: prerequisites, env vars, scenario usage, SLO table
- `loadtest/results/.gitkeep`
- `Makefile`: `load-test` (sustained 30 min + auto-analyze), `load-spike` targets; `LOAD_HOST` var

### B6.2 Observability Stack
- `infra/docker-compose.observability.yml`: Prometheus v2.51.0, Grafana 10.4.2, Loki 2.9.6, Promtail 2.9.6, Alertmanager v0.27.0
- `volumes`: `prom_data`, `grafana_data`, `loki_data` (new), `audit_logs` (external from B5.5)
- `secrets.grafana_password` bound to file `infra/secrets/grafana_password`
- `Makefile`: `obs-up`, `obs-down`, `obs-logs` targets

### B6.3 Prometheus Config
- `infra/observability/prometheus.yml`: 7 scrape jobs (m1–m5, m7-admin-be, m8), 15 s interval, 30d retention, alertmanager reference
- `infra/observability/alerts.yml`: 5 alert rules — `HighErrorRate` (5xx>5%, 5m), `HighP99Latency` (>3s, 10m), `M1SyncFailure` (offset diff, 5m), `DiskUsageHigh` (>85%, 15m), `CircuitBreakerOpen` (state==1, 2m)

### B6.4 Grafana Dashboards
- `infra/observability/grafana/provisioning/datasources/ds.yml`: Prometheus (default) + Loki
- `infra/observability/grafana/provisioning/dashboards/dashboards.yml`: file provider → `/var/lib/grafana/dashboards`
- `infra/observability/grafana/dashboards/rag-overview.json`: `schemaVersion:39`, `uid:"rag-llm-overview"`, 12 panels across 4 rows
  - Row 1: Gateway QPS + Gateway p95 Latency
  - Row 2: M3 Embedding Throughput + M3 Queue Depth
  - Row 3: M4 RAG Latency p50/p95/p99 + Circuit Breaker State (stat panel with color map)
  - Row 4: Pipeline Success/Fail + MySQL Sync Status
  - All panel titles/legends in English

### B6.5 Loki + Promtail
- `infra/observability/loki-config.yml`: single-node filesystem storage, schema v13, 30d retention (720h), compactor enabled
- `infra/observability/promtail-config.yml`: pushes to `loki:3100`; `rag-audit` job scrapes `/var/log/rag-audit/*.jsonl` with JSON parse + Unix timestamp + `action` label; `system-logs` job

### B6.6 Alertmanager
- `infra/observability/alertmanager.yml`: route groups by `alertname`+`severity`, 30 s group_wait, 1 h repeat; webhook to `m7-admin-backend:8000/admin/alerts/webhook`

### Secrets
- `infra/secrets/grafana_password.example`: placeholder for Grafana admin password

### Validation
- All 8 YAML files: `python3 yaml.safe_load` — **all pass**
- `rag-overview.json`: `json.load` — **pass** (12 panels, schemaVersion 39)
- Python files: `py_compile` — **all pass** (locustfile.py, analyze.py, spike.py, sustained.py)

---

**Phase B complete.** All B1–B6 items implemented.
