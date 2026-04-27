# M4 RAG Engine

Retrieval-Augmented Generation: queries pgvector for relevant chunks, builds context graph via Neo4j, calls vLLM for answer generation.

- **Port**: 8104
- **Run**: `uvicorn app.main:app --reload --port 8104`
- **Mock**: `MODULE_IMPL=mock uvicorn mocks.mock_server:app --port 8104`
- **Test**: `pytest -q`
