# M2 Doc-to-MD Progress

## Phase B1 — 2026-04-27

**항목:** a, b, c, d, e, f (전체 완료)

| 항목 | 내용 | 상태 |
|------|------|------|
| B1.a | Redis 분산 lock (`app/pipeline/lock.py`) — acquire/release, NX+TTL, owner 검증 | 완료 |
| B1.b | DLQ (`app/pipeline/dlq.py`) — push/pop_eligible, retry_count<3, next_retry backoff | 완료 |
| B1.c | `/ingest/scan` BackgroundTasks + `/ingest/status/{jid}` (`app/routers/ingest.py` 재작성) | 완료 |
| B1.d | Path traversal + symlink 차단 (`app/pipeline/scanner.py`) — followlinks=False, resolve 검증 | 완료 |
| B1.e | M3 trigger 3회 retry + exponential backoff + 최종 실패 시 DLQ push (`app/pipeline/run.py`) | 완료 |
| B1.f | Prometheus 메트릭 (`app/metrics.py`) — documents_processed, conversion_duration, m3_trigger_latency; `/metrics` 마운트 | 완료 |

**테스트 변화:** 1 → 20 passed (0 failed)
- `tests/conftest.py` — fakeredis autouse fixture
- `tests/test_lock.py` — 5 tests (acquire, duplicate reject, release, wrong-owner no-op, independent keys)
- `tests/test_dlq.py` — 5 tests (push/pop, future retry, max retry_count, increment pattern, partial eligibility)
- `tests/test_scan_endpoint.py` — 4 tests (job_id 반환, unknown status, done status, error status)
- `tests/test_scanner_security.py` — 5 tests (symlink skip, normal include, path escape, ext filter, incremental)

**의존성 추가:** `redis>=5.0`, `prometheus-client>=0.20` (pyproject.toml)

**skip:** MIME 검증 (libmagic 의존성) — Phase B 후반 예정

**다음: B2** — M3/M4 정합성 (batch_size 동적 조정 + hybrid 검색 튜닝 + 세션 히스토리)
