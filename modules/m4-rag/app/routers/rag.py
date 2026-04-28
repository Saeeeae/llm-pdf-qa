"""RAG endpoint.

Query → coarse retrieve → rerank → MMR → expand-to-parent → LLM.
Streams via SSE when ?stream=1; otherwise returns a JSON envelope.

Citation validation: any [n] in the LLM output where n exceeds the number of
sources actually included in the prompt is dropped to suppress hallucinated
citations.

Empty-result refusal: when retrieval returns nothing we still call the LLM,
but with a refusal-only system prompt (see prompt.SYS_REFUSE), so the model
won't fabricate from training data.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.embed_client import QueryEmbedder
from app.llm_client import generate_stream
from app.prompt import build, validate_citations
from app.retriever import RERANK_K, hybrid_search

router = APIRouter(prefix="/rag")


class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    top_k: int = Field(default=RERANK_K, ge=1, le=50)
    folder: Optional[str] = None  # L1: restrict to a folder prefix


def _source_payload(s: dict, idx: int) -> dict:
    return {
        "n": idx,
        "id": s["id"],
        "doc_id": s["doc_id"],
        "chunk_id": s["chunk_idx"],
        "parent_id": s.get("parent_id"),
        "folder_path": s.get("folder_path"),
        "score": float(s.get("score", 0.0)),
        "ce": s.get("ce"),
        "rrf": s.get("rrf"),
        "snippet": (s.get("leaf_text") or s.get("text", ""))[:200],
    }


@router.post("/query")
async def query(
    body: QueryRequest,
    stream: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    history = None
    if body.session_id:
        try:
            from app.session import get_history
            history = await get_history(body.session_id)
        except Exception:
            history = None

    # Run model inference in a thread so it doesn't block the event loop —
    # blocking on .encode() freezes every concurrent request.
    emb = await asyncio.to_thread(lambda: QueryEmbedder.get().encode(body.query))
    sources = await hybrid_search(
        db, body.query, emb, k=body.top_k, folder_filter=body.folder
    )
    msgs, kept = build(body.query, sources, history=history)
    sources_payload = [_source_payload(s, i + 1) for i, s in enumerate(sources[:kept])]
    refused = kept == 0

    if not stream:
        chunks = []
        async for tok in generate_stream(msgs):
            chunks.append(tok)
        answer = "".join(chunks)
        cleaned, dropped = validate_citations(answer, kept)

        if body.session_id:
            try:
                from app.session import add_turn
                await add_turn(body.session_id, body.query, cleaned)
            except Exception:
                pass

        return {
            "answer": cleaned,
            "sources": sources_payload,
            "refused": refused,
            "dropped_citations": dropped,
        }

    async def sse():
        yield (
            "event: meta\n"
            f"data: {json.dumps({'refused': refused, 'kept': kept})}\n\n"
        )
        yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
        tokens: list[str] = []
        async for tok in generate_stream(msgs):
            tokens.append(tok)
            yield f"event: token\ndata: {json.dumps({'token': tok}, ensure_ascii=False)}\n\n"

        full = "".join(tokens)
        cleaned, dropped = validate_citations(full, kept)
        yield (
            "event: done\n"
            f"data: {json.dumps({'dropped_citations': dropped}, ensure_ascii=False)}\n\n"
        )

        if body.session_id:
            try:
                from app.session import add_turn
                await add_turn(body.session_id, body.query, cleaned)
            except Exception:
                pass

    return StreamingResponse(sse(), media_type="text/event-stream")
