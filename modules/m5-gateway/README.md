# M5 Gateway

API Gateway: 외부 진입점. JWT 검증 → 다운스트림 라우팅 → rate limit / circuit breaker / 보안 헤더 / 감사 로그.

- **Port (host)**: 8080 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run`
- **Test**: `make test`
- **Logs**: `make log`
