# M3 Chunk / Embed

문서(Markdown) → **계층적 청킹 (parent + leaf)** → BGE-M3 임베딩 → PostgreSQL(pgvector) 저장.
M2가 만든 마크다운을 입력으로 받아 검색용 leaf 청크에 임베딩을 생성하고, LLM 컨텍스트 확장용 parent 청크도 같이 저장합니다.

- **Port (host)**: 8103 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run`
- **Test**: `make test`
- **Migrate**: `make migrate` (alembic upgrade head — required before first run)
- **Logs**: `make log`
