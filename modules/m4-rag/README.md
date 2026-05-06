# M4 RAG Engine

쿼리 → **하이브리드 검색 (vec + BM25 + RRF) → 크로스인코더 재순위 → MMR 다이버시티 → parent 청크 확장 → vLLM 답변 생성**.

- **Port (host)**: 8104 → 8000 (container)
- **Build**: `make build`
- **Run**: `make run`
- **Test**: `make test`
- **Logs**: `make log`
