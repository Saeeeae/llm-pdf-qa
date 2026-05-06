# M5 Gateway

API Gateway: validates JWT tokens (via M1), routes chat requests to M4 RAG engine, and exposes the public API for M6 UI.

- **Port (host)**: 8080 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run`
- **Test**: `make test`
- **Logs**: `make log`
