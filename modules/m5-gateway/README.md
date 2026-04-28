# M5 Gateway

API Gateway: 외부 진입점. JWT 검증 → 다운스트림 라우팅 → rate limit / circuit breaker / 보안 헤더 / 감사 로그.

- **Port**: 8080 (호스트 + 컨테이너 동일)
- **Run (host)**: `make run`
- **Run (Docker)**: `make docker-up` 또는 루트의 `make up`
- **Test**: `make test`

## 책임 분리

| 책임 | 위치 |
|------|------|
| JWT 검증 (HS256, 32자+ 시크릿) | `app/middleware/auth.py` |
| Rate limit (Redis sliding window) | `app/middleware/ratelimit.py` |
| Security headers (CSP, X-Frame-Options 등) | `app/middleware/security.py` |
| Tracing (X-Request-ID 전파) | `app/middleware/tracing.py` |
| 다운스트림 호출 (httpx) | `app/clients/downstream.py` |
| Audit log (PII 해시, 결과 구조화) | `app/audit.py` |
| Routing | `app/routers/{gateway,chat}.py` |

## 라우팅 맵

| 경로 prefix | 다운스트림 |
|------------|-----------|
| `/api/v1/auth/*` | `M1_URL` (m1-identity) |
| `/api/v1/chat` | `M4_URL` (m4-rag, SSE pass-through) |
| `/api/v1/admin/*` | `M7_URL` (m7-admin, requires `admin.read`) |
| `/api/v1/web-search/*` | `M8_URL` (m8-web-search, admin only) |
| `/api/v1/ingest/*` | `M2_URL` (admin only) |

## 환경 변수

| 변수 | 기본 | 설명 |
|------|-----|------|
| `JWT_SECRET` | _(필수)_ | 32자 이상. Docker secret으로 주입 시 `JWT_SECRET_FILE` 사용 |
| `ALLOWED_ORIGINS` | `http://m6-ui:3000` | **CORS allowlist (와일드카드 + credentials은 거부)**. 콤마구분 |
| `REDIS_URL` | `redis://redis:6379/0` | rate limit 백엔드 |
| `M1_URL`/`M2_URL`/`M3_URL`/`M4_URL`/`M7_URL`/`M8_URL` | `http://m<N>-...:8000` | 다운스트림 |
| `METRICS_USER` / `METRICS_PASSWORD` | `metrics` / _(빈 값=dev mode 허용)_ | `/metrics` Basic Auth |
| `M5_AUDIT_HASH_SALT` | `m5-gateway` | PII 해시 솔트 |

## 헬스 체크

```bash
curl http://localhost:8080/health   # liveness
curl http://localhost:8080/ready    # m1, m4 critical / m2,m3,m7,m8 optional
curl -u metrics:$METRICS_PASSWORD http://localhost:8080/metrics
```

`/ready` 응답:
- `{"status":"ok"}` 모든 다운스트림 OK
- `{"status":"degraded","failed":["m8"]}` optional만 실패
- `{"status":"unavailable","failed":["m1"]}` + 503 critical 실패

## 운영 노트

- **CORS 와일드카드 금지**: `ALLOWED_ORIGINS=*` 으로 두고 credentials를 보내면 브라우저가 거부 (CORS 스펙). 명시적 도메인 리스트만 허용.
- **회로차단기**: 다운스트림 5회 연속 실패 → 30초 차단 (per-target). `app/clients/downstream.py:CircuitBreaker`.
- **감사 로그**: 모든 인증된 요청에 user_id 해시 + path + status + latency 기록. stdout JSON.
