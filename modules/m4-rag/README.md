# M4 RAG Engine

Retrieval-Augmented Generation: queries pgvector for relevant chunks, builds context graph via Neo4j, calls vLLM for answer generation.

- **Port (host)**: 8104 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run`
- **Test**: `make test`
- **Logs**: `make log`
