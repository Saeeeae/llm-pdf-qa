import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.embed_client import QueryEmbedder
from app.retriever import hybrid_search
from app.llm_client import generate_stream
from app.prompt import build

router = APIRouter(prefix="/rag")


class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    top_k: int = 8


@router.post("/query")
async def query(
    body: QueryRequest,
    stream: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    # B2.4 — load session history if session_id provided
    history = None
    if body.session_id:
        try:
            from app.session import get_history
            history = await get_history(body.session_id)
        except Exception:
            history = None

    emb = QueryEmbedder.get().encode(body.query)
    sources = await hybrid_search(db, body.query, emb, k=body.top_k)

    sources_payload = [
        {
            "id": s["id"],
            "doc_id": s["doc_id"],
            "chunk_id": s["chunk_idx"],
            "score": float(s.get("rrf", 0)),
            "snippet": s["text"][:200],
        }
        for s in sources
    ]
    msgs = build(body.query, sources, history=history)

    if not stream:
        chunks = []
        async for tok in generate_stream(msgs):
            chunks.append(tok)
        answer = "".join(chunks)

        # B2.4 — persist turn to session history
        if body.session_id:
            try:
                from app.session import add_turn
                await add_turn(body.session_id, body.query, answer)
            except Exception:
                pass

        return {"answer": answer, "sources": sources_payload}

    async def sse():
        yield f"event: sources\ndata: {json.dumps(sources_payload)}\n\n"
        tokens: list[str] = []
        async for tok in generate_stream(msgs):
            tokens.append(tok)
            yield f"event: token\ndata: {json.dumps({'token': tok})}\n\n"
        yield "event: done\ndata: {}\n\n"

        # B2.4 — persist turn after streaming completes
        if body.session_id:
            try:
                from app.session import add_turn
                await add_turn(body.session_id, body.query, "".join(tokens))
            except Exception:
                pass

    return StreamingResponse(sse(), media_type="text/event-stream")
