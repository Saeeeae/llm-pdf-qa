import os
from typing import List, Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# B2.3 — configurable RRF constant and per-source weights
RRF_K = int(os.getenv("RRF_K", "60"))
VEC_WEIGHT = float(os.getenv("VEC_WEIGHT", "1.0"))
BM25_WEIGHT = float(os.getenv("BM25_WEIGHT", "1.0"))


async def hybrid_search(
    db: AsyncSession, query: str, embedding: List[float], k: int = 10
) -> List[Dict]:
    """Hybrid vector + BM25 retrieval with RRF fusion."""
    vec_rows = (
        await db.execute(
            text("""
                SELECT c.id, c.doc_id, c.chunk_idx, c.text, c.metadata,
                       1 - (c.embedding <=> :emb::vector) AS score
                FROM chunks c
                ORDER BY c.embedding <=> :emb::vector
                LIMIT :k
            """),
            {"emb": str(embedding), "k": k},
        )
    ).mappings().all()

    bm_rows = (
        await db.execute(
            text("""
                SELECT c.id, c.doc_id, c.chunk_idx, c.text, c.metadata,
                       ts_rank(c.text_tsv, plainto_tsquery('simple', :q)) AS score
                FROM chunks c
                WHERE c.text_tsv @@ plainto_tsquery('simple', :q)
                ORDER BY score DESC LIMIT :k
            """),
            {"q": query, "k": k},
        )
    ).mappings().all()

    rrf: Dict = {}
    for rank, r in enumerate(vec_rows):
        entry = rrf.setdefault(r["id"], {**dict(r), "rrf": 0.0})
        entry["rrf"] += VEC_WEIGHT / (RRF_K + rank)
    for rank, r in enumerate(bm_rows):
        entry = rrf.setdefault(r["id"], {**dict(r), "rrf": 0.0})
        entry["rrf"] += BM25_WEIGHT / (RRF_K + rank)

    fused = sorted(rrf.values(), key=lambda x: x["rrf"], reverse=True)[:k]
    return fused
