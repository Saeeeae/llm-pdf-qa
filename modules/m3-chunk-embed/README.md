# M3 Chunk/Embed

Chunks Markdown documents and generates vector embeddings stored in pgvector.

- **Port (host)**: 8103 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run`
- **Test**: `make test`
- **Migrate**: `make migrate` (alembic upgrade head — required before first run)
- **Logs**: `make log`
