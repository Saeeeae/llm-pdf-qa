import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.embedder import Embedder
from app.chunker import Chunker

router = APIRouter()
_embedder: Embedder | None = None
_chunker: Chunker | None = None

# B2.1 — concurrency limiter
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
    """Return an async Redis client (None if redis not available)."""
    try:
        import redis.asyncio as aredis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return aredis.from_url(redis_url, decode_responses=True)
    except Exception:
        return None


class ChunkEmbedRequest(BaseModel):
    doc_id: str
    markdown_path: str
    source_hash: str | None = None


@router.post("/chunk-embed")
async def chunk_embed(body: ChunkEmbedRequest, bg: BackgroundTasks, request: Request):
    # B2.1 — idempotency check
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
                    # Key already existed — duplicate request
                    return {"doc_id": body.doc_id, "status": "duplicate"}
            except Exception:
                # Redis unavailable — proceed without deduplication
                pass

    bg.add_task(_run, body.doc_id, body.markdown_path)
    return {"doc_id": body.doc_id, "status": "queued"}


async def _run(doc_id: str, md_path: str):
    from app.db import AsyncSessionLocal

    async with _SEM:
        md = Path(md_path)
        if not md.exists():
            return

        # Mark as started
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
            body = content.split("---", 2)[2] if content.startswith("---") else content

            pieces = get_chunker().chunk(body)
            if not pieces:
                async with AsyncSessionLocal() as s:
                    await s.execute(
                        text(
                            "UPDATE documents SET m3_status='done', chunk_count=0, "
                            "updated_at=NOW() WHERE doc_id=:d"
                        ),
                        {"d": doc_id},
                    )
                    await s.commit()
                return

            embeds = get_embedder().encode([p[0] for p in pieces])

            async with AsyncSessionLocal() as s:
                for idx, ((txt, h), emb) in enumerate(zip(pieces, embeds)):
                    await s.execute(
                        text(
                            "INSERT INTO chunks(doc_id, chunk_idx, chunk_hash, text, embedding) "
                            "VALUES (:d, :i, :h, :t, :e) "
                            "ON CONFLICT (chunk_hash) DO NOTHING"
                        ),
                        {"d": doc_id, "i": idx, "h": h, "t": txt, "e": str(emb)},
                    )
                await s.execute(
                    text(
                        "UPDATE documents SET m3_status='done', chunk_count=:c, "
                        "updated_at=NOW() WHERE doc_id=:d"
                    ),
                    {"c": len(pieces), "d": doc_id},
                )
                await s.commit()

        except Exception as exc:
            # B2.1 — error state with message
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
