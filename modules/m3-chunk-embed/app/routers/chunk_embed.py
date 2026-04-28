"""Chunking + embedding pipeline.

For each markdown produced by m2:
1. Parse frontmatter (L1 structural metadata).
2. Hierarchical chunking: parent chunks (~1024 tok) + leaf chunks (~256 tok).
3. Persist parents in `parent_chunks`; embed and persist leaves in `chunks`
   with parent_id, folder_path, and a metadata JSONB blob carrying frontmatter
   + hierarchical position info.

Idempotency is keyed on (doc_id, source_hash). Re-running with an unchanged
hash is a no-op via Redis SETNX (24h TTL).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunker import Chunker
from app.db import get_db
from app.embedder import Embedder

router = APIRouter()
_embedder: Embedder | None = None
_chunker: Chunker | None = None

_SEM = asyncio.Semaphore(int(os.getenv("M3_MAX_CONCURRENT", "2")))


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def get_chunker() -> Chunker:
    global _chunker
    if _chunker is None:
        _chunker = Chunker()
    return _chunker


def _get_redis():
    try:
        import redis.asyncio as aredis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return aredis.from_url(redis_url, decode_responses=True)
    except Exception:
        return None


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Strip YAML-ish frontmatter and return (metadata_dict, body).

    Frontmatter format produced by m2 is `key: value` lines between two `---`
    fences. We don't pull in PyYAML for one-line parsing.
    """
    if not content.startswith("---"):
        return {}, content
    # Find the closing fence
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    raw = content[3:end].strip()
    body = content[end + 4 :].lstrip("\n")
    meta: dict = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    return meta, body


class ChunkEmbedRequest(BaseModel):
    doc_id: str
    markdown_path: str
    source_hash: str | None = None


@router.post("/chunk-embed")
async def chunk_embed(body: ChunkEmbedRequest, bg: BackgroundTasks, request: Request):
    idem_key = request.headers.get("X-Idempotency-Key")
    if not idem_key and body.source_hash:
        idem_key = f"{body.doc_id}:{body.source_hash}"

    if idem_key:
        r = _get_redis()
        if r is not None:
            redis_key = f"m3:idem:{idem_key}"
            try:
                set_result = await r.set(redis_key, "1", nx=True, ex=86400)
                await r.aclose()
                if not set_result:
                    return {"doc_id": body.doc_id, "status": "duplicate"}
            except Exception:
                pass

    bg.add_task(_run, body.doc_id, body.markdown_path)
    return {"doc_id": body.doc_id, "status": "queued"}


async def _run(doc_id: str, md_path: str):
    from app.db import AsyncSessionLocal

    async with _SEM:
        md = Path(md_path)
        if not md.exists():
            return

        async with AsyncSessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO documents(doc_id, m3_status, m3_started_at) "
                    "VALUES (:d, 'processing', NOW()) "
                    "ON CONFLICT (doc_id) DO UPDATE SET m3_status='processing', "
                    "m3_started_at=NOW(), updated_at=NOW()"
                ),
                {"d": doc_id},
            )
            await s.commit()

        try:
            content = md.read_text(encoding="utf-8")
            front, body = _parse_frontmatter(content)
            folder_path = front.get("folder_path") or None
            source_path = front.get("source_path") or None

            parents, leaves = get_chunker().chunk(body)

            if not leaves:
                async with AsyncSessionLocal() as s:
                    await s.execute(
                        text(
                            "UPDATE documents SET m3_status='done', chunk_count=0, "
                            "folder_path=:fp, doc_meta=:meta::jsonb, "
                            "updated_at=NOW() WHERE doc_id=:d"
                        ),
                        {
                            "d": doc_id,
                            "fp": folder_path,
                            "meta": _json(front),
                        },
                    )
                    await s.commit()
                return

            # Embed leaves only (parents are LLM-context, not retrieval targets).
            leaf_embeds = get_embedder().encode([leaf.text for leaf in leaves])

            async with AsyncSessionLocal() as s:
                # Update document-level metadata first.
                await s.execute(
                    text(
                        "UPDATE documents SET folder_path=:fp, doc_meta=:meta::jsonb, "
                        "source_path=COALESCE(:sp, source_path), "
                        "updated_at=NOW() WHERE doc_id=:d"
                    ),
                    {
                        "d": doc_id,
                        "fp": folder_path,
                        "sp": source_path,
                        "meta": _json(front),
                    },
                )

                # Insert parents and capture generated ids.
                # Use a single round-trip per parent (small N, ~few dozen).
                parent_id_map: dict[int, int] = {}
                for p in parents:
                    pmeta = {
                        "level": "parent",
                        "start_token": p.start,
                        "end_token": p.end,
                        **front,
                        **(p.metadata or {}),  # heading_path from section split
                    }
                    row = (
                        await s.execute(
                            text(
                                "INSERT INTO parent_chunks(doc_id, chunk_idx, text, metadata) "
                                "VALUES (:d, :i, :t, :m::jsonb) "
                                "ON CONFLICT (doc_id, chunk_idx) DO UPDATE "
                                "SET text=EXCLUDED.text, metadata=EXCLUDED.metadata "
                                "RETURNING id"
                            ),
                            {"d": doc_id, "i": p.idx, "t": p.text, "m": _json(pmeta)},
                        )
                    ).first()
                    parent_id_map[p.idx] = row[0]

                # Insert leaves with parent_id, folder_path, embedding, metadata.
                # The persisted chunk_hash is salted with (doc_id, chunk_idx)
                # so identical paragraphs across docs (license footers, shared
                # policy text) don't collide and silently drop.
                # On re-runs of the same doc/chunk we UPDATE so parent_id and
                # metadata stay in sync with the latest section split.
                import hashlib as _hashlib
                for leaf, emb in zip(leaves, leaf_embeds):
                    lmeta = {
                        "level": "leaf",
                        "start_token": leaf.start,
                        "end_token": leaf.end,
                        "parent_idx": leaf.parent_idx,
                        **front,
                        **(leaf.metadata or {}),
                    }
                    salted_hash = _hashlib.sha256(
                        f"{doc_id}|{leaf.idx}|{leaf.text}".encode("utf-8")
                    ).hexdigest()
                    await s.execute(
                        text(
                            "INSERT INTO chunks(doc_id, chunk_idx, chunk_hash, text, "
                            "embedding, parent_id, folder_path, metadata) "
                            "VALUES (:d, :i, :h, :t, :e, :pid, :fp, :m::jsonb) "
                            "ON CONFLICT (chunk_hash) DO UPDATE SET "
                            "  text = EXCLUDED.text, "
                            "  embedding = EXCLUDED.embedding, "
                            "  parent_id = EXCLUDED.parent_id, "
                            "  folder_path = EXCLUDED.folder_path, "
                            "  metadata = EXCLUDED.metadata"
                        ),
                        {
                            "d": doc_id,
                            "i": leaf.idx,
                            "h": salted_hash,
                            "t": leaf.text,
                            "e": str(emb),
                            "pid": parent_id_map.get(leaf.parent_idx),
                            "fp": folder_path,
                            "m": _json(lmeta),
                        },
                    )

                await s.execute(
                    text(
                        "UPDATE documents SET m3_status='done', chunk_count=:c, "
                        "updated_at=NOW() WHERE doc_id=:d"
                    ),
                    {"c": len(leaves), "d": doc_id},
                )
                await s.commit()

        except Exception as exc:
            try:
                async with AsyncSessionLocal() as s:
                    await s.execute(
                        text(
                            "UPDATE documents SET m3_status='error', error_msg=:e, "
                            "updated_at=NOW() WHERE doc_id=:d"
                        ),
                        {"e": str(exc)[:2048], "d": doc_id},
                    )
                    await s.commit()
            except Exception:
                pass
            raise


def _json(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False)


@router.get("/status/{doc_id}")
async def status(doc_id: str, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            text("SELECT m3_status, chunk_count FROM documents WHERE doc_id=:d"),
            {"d": doc_id},
        )
    ).first()
    if not row:
        raise HTTPException(404, detail="doc_id not found")
    return {"doc_id": doc_id, "status": row[0], "chunks": row[1]}
