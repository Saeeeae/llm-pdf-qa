# M7 Admin Backend

관리자 API: 시스템 헬스 집계, 감사 로그 조회, 사용자/파이프라인 관리, 메트릭 노출, WebSocket 이벤트.

- **Port**: 8107 (호스트), 8000 (컨테이너 내부)
- **Run (host)**: `make run`
- **Run (Docker)**: `make docker-up` 또는 루트의 `make up`
- **Test**: `make test`

## 엔드포인트

| 경로 | 권한 | 설명 |
|------|------|------|
| `GET /admin/health/aggregate` | `admin.read` | 모든 모듈의 `/ready` 집계 |
| `GET /admin/audit_log` | `audit.read` | 감사 로그 조회 (필터/페이지네이션) |
| `GET /admin/users` | `admin.read` | M1 사용자 목록 read-only 미러 |
| `GET /admin/metrics/summary` | `admin.read` | Prometheus 메트릭 요약 |
| `GET /admin/gpu/stats` | `admin.read` | nvidia-smi 결과 (없으면 graceful skip) |
| `POST /admin/pipeline/trigger` | `admin.write` | M2 ingest 수동 트리거 |
| `WS /admin/ws` | `admin.read` | Redis pubsub(audit_events, pipeline_events) 푸시 |

## 환경 변수

| 변수 | 기본 | 설명 |
|------|-----|------|
| `POSTGRES_URL` | `postgresql+asyncpg://...@postgres:5432/ragdb` | 메인 DB (read/write) |
| `POSTGRES_RO_URL` | `postgresql+asyncpg://postgres_ro:postgres@postgres:5432/ragdb` | 읽기 전용 (감사/사용자 목록용) |
| `REDIS_URL` | `redis://redis:6379/0` | 캐시 + WebSocket pubsub |
| `JWT_SECRET` | _(필수)_ | M5와 동일 시크릿 (또는 Docker secret) |
| `JWT_ALGORITHM` | `HS256` | RS256 사용 시 변경 |
| `M1_URL`/`M2_URL`/`M3_URL`/`M4_URL`/`M5_URL` | `http://m<N>-...:8000` | 헬스 집계용 다운스트림 |
| **`WS_ALLOW_QUERY_TOKEN`** | `0` | **0=권장**. 1로 두면 `?token=...` 쿼리 파라미터로 WS 인증 허용 (token이 access log에 누수되므로 폐쇄망/legacy 클라이언트만) |

## WebSocket 토큰 추출 우선순위

1. `Authorization: Bearer <token>` 헤더 (권장)
2. `Sec-WebSocket-Protocol: bearer, <token>` (브라우저 친화적)
3. `?token=...` 쿼리 (기본 비활성, `WS_ALLOW_QUERY_TOKEN=1`로 옵트인)

## 운영 노트

- **WS 토큰 누수 방지**: 쿼리 파라미터 모드는 access log에 토큰이 그대로 남으므로 production에서는 끄세요.
- **postgres_ro**: 감사/사용자 조회용 별도 read-only DB 유저. 미설정 시 `POSTGRES_URL`로 fallback.
- **nvidia-smi**: 컨테이너에 nvidia-smi 없으면 `/admin/gpu/stats`는 빈 응답으로 graceful degrade.
