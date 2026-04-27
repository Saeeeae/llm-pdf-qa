# M2 Doc-to-MD

Document ingestion service: scans source directories, converts documents to Markdown via kordoc, and stores state for downstream chunk/embed (M3).

- **Port**: 8102
- **Run**: `uvicorn app.main:app --reload --port 8102`
- **Mock**: `MODULE_IMPL=mock uvicorn mocks.mock_server:app --port 8102`
- **Test**: `pytest -q`
