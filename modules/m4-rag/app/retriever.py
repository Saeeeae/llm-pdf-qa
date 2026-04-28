"""Retrieval pipeline for m4-rag.

Stages
------
1. retrieve()          — coarse hybrid: pgvector cosine top-N + BM25 top-N → RRF fuse.
                          Returns up to RETRIEVE_K candidates.
2. rerank()            — BAAI/bge-reranker-v2-m3 cross-encoder over candidate texts.
                          Combined with RRF via RERANK_ALPHA: final = a*ce + (1-a)*rrf.
3. mmr_diversify()     — Maximal Marginal Relevance using leaf embeddings to avoid
                          same-doc clustering. Picks RERANK_K final results.
4. expand_to_parents() — Replace each leaf with its parent_chunks.text for the LLM,
                          deduplicating shared parents.
"""
from __future__ import annotations

import asyncio
import math
import os
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Tunables
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "40"))
RERANK_K = int(os.getenv("RERANK_K", "8"))
RRF_K = int(os.getenv("RRF_K", "60"))
VEC_WEIGHT = float(os.getenv("VEC_WEIGHT", "1.0"))
BM25_WEIGHT = float(os.getenv("BM25_WEIGHT", "1.0"))
RERANK_ALPHA = float(os.getenv("RERANK_ALPHA", "0.7"))   # weight on cross-encoder
MMR_LAMBDA = float(os.getenv("MMR_LAMBDA", "0.5"))       # 1.0=relevance only, 0.0=diversity only
USE_RERANKER = os.getenv("USE_RERANKER", "1") == "1"


# ─── Stage 1: hybrid retrieve (pgvector + BM25, RRF fuse) ──────────────────
async def retrieve(
    db: AsyncSession,
    query: str,
    embedding: List[float],
    k: int = RETRIEVE_K,
    folder_filter: Optional[str] = None,
    need_embedding: bool = True,
) -> List[Dict]:
    """Return up to k fused candidates.

    When `need_embedding=False` we skip the per-row `embedding::text` cast,
    which is significant overhead at scale (~10KB per 1024-dim vector × 2k
    candidates). Set this when MMR is disabled (MMR_LAMBDA == 1.0).
    """
    folder_clause = ""
    params = {"emb": str(embedding), "q": query, "k": k}
    if folder_filter:
        folder_clause = "AND c.folder_path LIKE :folder"
        params["folder"] = folder_filter + "%"

    emb_select = "c.embedding::text AS embedding," if need_embedding else "NULL AS embedding,"

    vec_rows = (
        await db.execute(
            text(f"""
                SELECT c.id, c.doc_id, c.chunk_idx, c.text, c.metadata,
                       c.parent_id, c.folder_path,
                       {emb_select}
                       1 - (c.embedding <=> :emb::vector) AS score
                FROM chunks c
                WHERE 1=1 {folder_clause}
                ORDER BY c.embedding <=> :emb::vector
                LIMIT :k
            """),
            params,
        )
    ).mappings().all()

    bm_rows = (
        await db.execute(
            text(f"""
                SELECT c.id, c.doc_id, c.chunk_idx, c.text, c.metadata,
                       c.parent_id, c.folder_path,
                       {emb_select}
                       ts_rank(c.text_tsv, plainto_tsquery('simple', :q)) AS score
                FROM chunks c
                WHERE c.text_tsv @@ plainto_tsquery('simple', :q) {folder_clause}
                ORDER BY score DESC LIMIT :k
            """),
            params,
        )
    ).mappings().all()

    rrf: Dict[int, Dict] = {}
    for rank, r in enumerate(vec_rows):
        entry = rrf.setdefault(r["id"], {**dict(r), "rrf": 0.0})
        entry["rrf"] += VEC_WEIGHT / (RRF_K + rank)
    for rank, r in enumerate(bm_rows):
        entry = rrf.setdefault(r["id"], {**dict(r), "rrf": 0.0})
        entry["rrf"] += BM25_WEIGHT / (RRF_K + rank)

    return sorted(rrf.values(), key=lambda x: x["rrf"], reverse=True)[:k]


# ─── Stage 2: cross-encoder rerank ─────────────────────────────────────────
def rerank(query: str, candidates: List[Dict], alpha: float = RERANK_ALPHA) -> List[Dict]:
    """Apply BGE cross-encoder; combine with RRF score; return re-sorted list.

    `final` becomes the new ranking signal; we keep `rrf` and `ce` for debug.
    Falls back to identity if reranker is disabled or unavailable.
    """
    if not USE_RERANKER or not candidates:
        for c in candidates:
            c["final"] = c.get("rrf", 0.0)
            c["ce"] = None
        return candidates

    try:
        from app.reranker import Reranker, normalize
        ce = Reranker.get().score(query, [c["text"] for c in candidates])
    except Exception:  # pragma: no cover
        # If reranker init/predict blows up at runtime, degrade gracefully.
        for c in candidates:
            c["final"] = c.get("rrf", 0.0)
            c["ce"] = None
        return candidates

    ce_norm = normalize(ce)
    rrf_norm = normalize([c.get("rrf", 0.0) for c in candidates])
    for c, ce_s, ce_n, rrf_n in zip(candidates, ce, ce_norm, rrf_norm):
        c["ce"] = ce_s
        c["final"] = alpha * ce_n + (1.0 - alpha) * rrf_n

    return sorted(candidates, key=lambda x: x["final"], reverse=True)


# ─── Stage 3: MMR diversification ──────────────────────────────────────────
def _parse_pgvector(s: str) -> List[float]:
    """pgvector serializes as '[0.1,0.2,...]' (no spaces in practice, but
    we strip per-token to stay defensive against driver/version differences)."""
    if not s:
        return []
    return [float(x) for x in (t.strip() for t in s.strip("[]").split(",")) if x]


def _cos(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


def mmr_diversify(
    candidates: List[Dict], k: int = RERANK_K, lambda_: float = MMR_LAMBDA
) -> List[Dict]:
    """Greedy MMR using leaf embeddings.

    score = λ * relevance(c) - (1-λ) * max_sim(c, selected)
    Embeddings are already L2-normalized (BGE-M3 with normalize=True).
    """
    if not candidates:
        return []
    pool = [dict(c) for c in candidates]
    embs = [_parse_pgvector(c["embedding"]) for c in pool]
    rel = [c.get("final", c.get("rrf", 0.0)) for c in pool]

    selected: List[int] = []
    remaining = set(range(len(pool)))

    while remaining and len(selected) < k:
        best_i, best_score = None, -1e9
        for i in remaining:
            if not selected:
                score = rel[i]
            else:
                max_sim = max(_cos(embs[i], embs[j]) for j in selected)
                score = lambda_ * rel[i] - (1.0 - lambda_) * max_sim
            if score > best_score:
                best_score = score
                best_i = i
        selected.append(best_i)
        remaining.remove(best_i)

    return [pool[i] for i in selected]


# ─── Stage 4: expand leaves to parent chunks for LLM context ───────────────
async def expand_to_parents(db: AsyncSession, leaves: List[Dict]) -> List[Dict]:
    """Resolve each leaf to its parent_chunks.text. Deduplicates parents (a single
    parent containing multiple selected leaves is emitted once with merged sources).
    """
    if not leaves:
        return []

    parent_ids = [leaf["parent_id"] for leaf in leaves if leaf.get("parent_id") is not None]
    parents_by_id: Dict[int, Dict] = {}
    if parent_ids:
        rows = (
            await db.execute(
                text(
                    "SELECT id, doc_id, chunk_idx, text, metadata "
                    "FROM parent_chunks WHERE id = ANY(:ids)"
                ),
                {"ids": parent_ids},
            )
        ).mappings().all()
        parents_by_id = {r["id"]: dict(r) for r in rows}

    out: List[Dict] = []
    seen: Dict[int, int] = {}  # parent_id -> index in out
    for leaf in leaves:
        pid = leaf.get("parent_id")
        parent = parents_by_id.get(pid) if pid is not None else None
        if parent and pid in seen:
            # Already emitted; keep best score & accumulate leaf chunk ids.
            existing = out[seen[pid]]
            existing["leaf_ids"].append(leaf["id"])
            existing["score"] = max(
                existing.get("score", 0.0),
                leaf.get("final", leaf.get("rrf", 0.0)),
            )
            continue

        text_for_llm = parent["text"] if parent else leaf["text"]
        item = {
            "id": leaf["id"],
            "doc_id": leaf["doc_id"],
            "chunk_idx": leaf["chunk_idx"],
            "parent_id": pid,
            "text": text_for_llm,
            "leaf_text": leaf["text"],
            "folder_path": leaf.get("folder_path"),
            "metadata": leaf.get("metadata") or {},
            "score": leaf.get("final", leaf.get("rrf", 0.0)),
            "ce": leaf.get("ce"),
            "rrf": leaf.get("rrf"),
            "leaf_ids": [leaf["id"]],
        }
        out.append(item)
        if parent:
            seen[pid] = len(out) - 1
    return out


# ─── Public entrypoint ─────────────────────────────────────────────────────
async def hybrid_search(
    db: AsyncSession,
    query: str,
    embedding: List[float],
    k: int = RERANK_K,
    folder_filter: Optional[str] = None,
) -> List[Dict]:
    """Backwards-compatible entrypoint used by routers/rag.py.

    Pipeline: retrieve(RETRIEVE_K) → rerank → mmr(k) → expand_to_parents.
    When MMR_LAMBDA >= 0.999 we skip the diversification step *and* the
    expensive embedding fetch in Stage 1 — a meaningful win for high-QPS dep-
    loys where diversity isn't a concern.
    """
    mmr_enabled = MMR_LAMBDA < 0.999
    candidates = await retrieve(
        db, query, embedding,
        k=RETRIEVE_K,
        folder_filter=folder_filter,
        need_embedding=mmr_enabled,
    )
    if not candidates:
        return []
    # rerank() runs the cross-encoder synchronously — offload to a thread so
    # we don't stall the event loop on GPU/CPU inference.
    if USE_RERANKER:
        reranked = await asyncio.to_thread(rerank, query, candidates)
    else:
        reranked = rerank(query, candidates)
    if mmr_enabled:
        final = mmr_diversify(reranked, k=k)
    else:
        final = reranked[:k]
    return await expand_to_parents(db, final)
