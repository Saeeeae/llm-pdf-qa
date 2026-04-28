# M4 RAG Engine

쿼리 → **하이브리드 검색 (vec + BM25 + RRF) → 크로스인코더 재순위 → MMR 다이버시티 → parent 청크 확장 → vLLM 답변 생성**.

- **Port**: 8104 (호스트), 8000 (컨테이너 내부)
- **Run (host)**: `make run`
- **Run (Docker)**: `make docker-up` 또는 루트의 `make up`
- **Test**: `make test`

## 검색 파이프라인

```
query
  │
  ├─ 1. QueryEmbedder.encode(q)              ← BGE-M3 (m3와 동일 캐시)
  │
  ├─ 2. retrieve(k=RETRIEVE_K=40)
  │     ├─ pgvector cosine top-40 (HNSW 인덱스)
  │     ├─ BM25 (tsvector) top-40
  │     └─ RRF fuse: VEC_WEIGHT/(RRF_K+rank) + BM25_WEIGHT/(RRF_K+rank)
  │     [optional folder_filter: WHERE folder_path LIKE '<prefix>%']
  │
  ├─ 3. rerank(USE_RERANKER=1)
  │     ├─ BAAI/bge-reranker-v2-m3 cross-encoder score (q, leaf.text)
  │     ├─ normalize CE 점수 + RRF 점수 → final = α·CE + (1-α)·RRF
  │     └─ α = RERANK_ALPHA (기본 0.7)
  │
  ├─ 4. mmr_diversify(k=RERANK_K=8)
  │     score = λ·final - (1-λ)·max_cos_sim(c, selected)
  │     λ = MMR_LAMBDA (기본 0.5)
  │
  ├─ 5. expand_to_parents
  │     leaf.parent_id → parent_chunks.text를 LLM 컨텍스트로 사용
  │     동일 부모 dedup (multiple leaves → one parent block)
  │
  ├─ 6. prompt.build(query, sources, history)
  │     ├─ 한국어 system prompt (SYS_REAL)
  │     ├─ sources 비면 → 거부 prompt (SYS_REFUSE)
  │     ├─ 토큰 budget = MAX_CONTEXT_TOKENS (char 기반 근사)
  │     └─ history 토큰 budget = HISTORY_TOKEN_BUDGET, 최대 MAX_HISTORY_TURNS turn
  │
  ├─ 7. vLLM stream (Qwen2.5 등) — circuit breaker 보호
  │
  └─ 8. validate_citations(answer, kept)
        [n] 인용 중 1..kept 범위 밖은 제거 (LLM 환각 인용 차단)
```

응답:
```json
{
  "answer": "...",
  "sources": [{"n":1, "doc_id":"...", "chunk_id":..., "parent_id":..., "score":..., "ce":..., "rrf":..., "snippet":"..."}],
  "refused": false,
  "dropped_citations": []
}
```

## 환경 변수

| 변수 | 기본 | 설명 |
|------|-----|------|
| **DB / Cache** | | |
| `POSTGRES_URL` | `postgresql+asyncpg://...@postgres:5432/ragdb` | m3와 동일 DB |
| `REDIS_URL` | `redis://redis:6379/0` | 세션 history |
| `SESSION_TTL` | `3600` | 세션 history TTL (초) |
| **vLLM** | | |
| `VLLM_URL` | `http://vllm:8000/v1` | OpenAI 호환 엔드포인트 |
| `VLLM_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | |
| `MAX_CONTEXT_TOKENS` | `6000` | 컨텍스트 토큰 budget |
| `CHARS_PER_TOKEN` | `2.0` | char→토큰 근사 (CJK 보수적) |
| `HISTORY_TOKEN_BUDGET` | `1500` | 대화 history 토큰 budget |
| `MAX_HISTORY_TURNS` | `10` | history 최대 turn 수 |
| **Embedding** | | |
| `EMBED_MODEL` | `BAAI/bge-m3` | m3와 동일 |
| `EMBED_DEVICE` | `auto` | auto/cpu/cuda:N |
| `HF_HOME` | `/data/models` | m3와 캐시 공유 |
| **Reranker** | | |
| `USE_RERANKER` | `1` | 0이면 RRF만으로 정렬 (CE 비활성) |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | cross-encoder |
| `RERANK_DEVICE` | `auto` | |
| `RERANK_ALPHA` | `0.7` | final = α·CE + (1-α)·RRF |
| **Retrieval** | | |
| `RETRIEVE_K` | `40` | 1단계 후보 수 |
| `RERANK_K` | `8` | 최종 LLM 입력 개수 |
| `RRF_K` | `60` | RRF 평탄화 상수 |
| `VEC_WEIGHT` | `1.0` | RRF에서 vector 가지 가중 |
| `BM25_WEIGHT` | `1.0` | RRF에서 BM25 가지 가중 |
| `MMR_LAMBDA` | `0.5` | 1.0=relevance만, 0.0=다양성만 |

## 엔드포인트

```bash
# 비-스트리밍 응답
curl -X POST http://localhost:8104/rag/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"인사 정책상 휴가 일수는?","top_k":8}'

# 폴더 필터 (L1 구조 활용)
curl -X POST http://localhost:8104/rag/query \
  -d '{"query":"휴가","folder":"hr/policy"}'

# SSE 스트리밍 (이벤트: meta, sources, token, done)
curl -N -X POST 'http://localhost:8104/rag/query?stream=1' \
  -H 'Content-Type: application/json' \
  -d '{"query":"...","session_id":"u123-s1"}'

# Health / Ready
curl http://localhost:8104/health
curl http://localhost:8104/ready    # DB + vLLM ping
```

## 운영 노트

- **첫 실행 모델 다운로드**:
  - BGE-M3 (~2.3GB)
  - BGE-reranker-v2-m3 (~600MB)
  - 모두 `/data/models` 공유 캐시. 폐쇄망에서는 사전 fetch.
- **alembic 없음**: m4는 m3가 만든 스키마를 read-only로 사용. parent_chunks는 m3-chunk-embed의 0003 마이그레이션에서 생성.
- **회로차단기**: vLLM 5회 연속 실패 시 30초 차단. `app/llm_client.py:CB`.
- **빈 결과 처리**: retrieval이 비면 `refused: true` + 거부 system prompt로 LLM 호출 → "제공된 문서에서 답을 찾을 수 없습니다" 응답.
- **인용 검증**: LLM이 `[5]`처럼 sources에 없는 번호를 만들면 응답에서 자동 제거. `dropped_citations`에 기록.
- **GPU 미보유**: `USE_RERANKER=0`로 reranker 끄거나 `RERANK_DEVICE=cpu`로 CPU 동작 (속도 ~3-5x 감소). embed/rerank 별도 device 지정 가능.
