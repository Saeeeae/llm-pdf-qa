# M7 Admin Backend

Administration API: system health aggregation, audit log, and metrics endpoint.

- **Port**: 8107
- **Run**: `uvicorn app.main:app --reload --port 8107`
- **Mock**: `MODULE_IMPL=mock uvicorn mocks.mock_server:app --port 8107`
- **Test**: `pytest -q`
