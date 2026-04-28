# M3 Chunk / Embed

문서(Markdown) → **계층적 청킹 (parent + leaf)** → BGE-M3 임베딩 → PostgreSQL(pgvector) 저장.
M2가 만든 마크다운을 입력으로 받아 검색용 leaf 청크에 임베딩을 생성하고, LLM 컨텍스트 확장용 parent 청크도 같이 저장합니다.

- **Port**: 8103 (호스트), 8000 (컨테이너 내부)
- **Run (host)**: `make run` → `uvicorn app.main:app --port 8103`
- **Run (Docker)**: `make docker-up` 또는 루트의 `make up`
- **Test**: `make test`

## 데이터 흐름

```
m2 → POST /chunk-embed { doc_id, markdown_path, source_hash }
        │
        ├─ 1. Idempotency: Redis SETNX(m3:idem:{doc_id}:{source_hash}) — 24h TTL
        ├─ 2. Frontmatter parse → documents.doc_meta JSONB
        ├─ 3. Hierarchical chunk:
        │       parent_chunks: ~1024 tok (LLM 컨텍스트용, 임베딩 없음)
        │       chunks       : ~256 tok  (검색용, 임베딩 있음, parent_id FK)
        ├─ 4. Embedder.encode(leaves) — BGE-M3 normalize=True
        └─ 5. Bulk insert with ON CONFLICT(chunk_hash) DO NOTHING
              → documents.m3_status='done', chunk_count=len(leaves)
```

## 스키마 (alembic)

| 마이그레이션 | 변경 |
|-------------|------|
| 0001_initial | `documents`, `chunks`(embedding ARRAY→vector(1024), tsvector GENERATED, ivfflat 인덱스) |
| 0002_add_error_msg | `documents.error_msg`, `documents.m3_started_at` |
| 0003_parent_chunks_hnsw | `parent_chunks` 신규, `chunks.parent_id`/`folder_path`, `documents.folder_path`/`doc_meta`, **ivfflat → HNSW** (m=16, ef_construction=64) |

`make migrate`(루트)로 컨테이너 안에서 alembic 실행.

## 환경 변수

| 변수 | 기본 | 설명 |
|------|-----|------|
| `POSTGRES_URL` | `postgresql+asyncpg://postgres:postgres@postgres:5432/ragdb` | DB 연결 |
| `REDIS_URL` | `redis://redis:6379/0` | 멱등성 락 |
| `EMBED_MODEL` | `BAAI/bge-m3` | 임베딩 모델 |
| `EMBED_DEVICE` | `auto` | `auto`(GPU 있으면 cuda:0, 없으면 cpu) / `cpu` / `cuda:N` |
| `HF_HOME` / `TRANSFORMERS_CACHE` / `SENTENCE_TRANSFORMERS_HOME` | `/data/models` | 모델 캐시 (호스트 바인드 마운트) |
| `PARENT_CHUNK_SIZE` | `1024` | parent 청크 토큰 길이 |
| `PARENT_CHUNK_OVERLAP` | `100` | parent 오버랩 |
| `CHUNK_SIZE` | `256` | leaf 청크 토큰 길이 |
| `CHUNK_OVERLAP` | `32` | leaf 오버랩 |
| `M3_MAX_CONCURRENT` | `2` | 동시 처리 가능한 doc 수 (Semaphore) |

청크 크기 가이드:
- `parent_size > leaf_size` 강제 (생성자 검증)
- BGE-M3 max는 8192 토큰, 기본 1024는 안전 범위
- 검색 정밀도 위해 leaf는 작게(256), LLM 컨텍스트 풍부하게 위해 parent는 크게(1024)

## 엔드포인트

```bash
# 청킹 + 임베딩 트리거 (m2가 자동 호출)
curl -X POST http://localhost:8103/chunk-embed \
  -H "X-Idempotency-Key: doc-abc-v1" \
  -d '{"doc_id":"doc-abc","markdown_path":"/data/markdown/policy/HR.md","source_hash":"abc123"}'

# 상태
curl http://localhost:8103/status/doc-abc
# → {"doc_id":"doc-abc","status":"done","chunks":42}

# Liveness / Readiness
curl http://localhost:8103/health
curl http://localhost:8103/ready    # DB ping
```

## 운영 노트

- **첫 실행**: BGE-M3(약 2.3GB)가 `/data/models`에 다운로드됨. 폐쇄망에서는 사전 fetch 필요.
- **GPU 미보유**: `EMBED_DEVICE=cpu` 또는 `auto`로 자동 fallback. 처리량 ~10x 감소.
- **HNSW vs ivfflat**: 0003 마이그레이션 후 HNSW. lists/probes 튜닝 불필요. ef_search는 쿼리 시 SET으로 조정.
- **재인덱싱**: 같은 `doc_id`로 재호출 시 parent_chunks는 `ON CONFLICT DO UPDATE`로 갱신, leaves는 chunk_hash UNIQUE 충돌 시 skip → 텍스트 변경 시 hash가 달라지므로 새 leaf 들어감.
