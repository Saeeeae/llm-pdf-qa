# M5 Gateway

API Gateway: validates JWT tokens (via M1), routes chat requests to M4 RAG engine, and exposes the public API for M6 UI.

- **Port**: 8080
- **Run**: `uvicorn app.main:app --reload --port 8080`
- **Mock**: `MODULE_IMPL=mock uvicorn mocks.mock_server:app --port 8080`
- **Test**: `pytest -q`
