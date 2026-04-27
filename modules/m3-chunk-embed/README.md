# M3 Chunk/Embed

Chunks Markdown documents and generates vector embeddings stored in pgvector.

- **Port**: 8103
- **Run**: `uvicorn app.main:app --reload --port 8103`
- **Mock**: `MODULE_IMPL=mock uvicorn mocks.mock_server:app --port 8103`
- **Test**: `pytest -q`
