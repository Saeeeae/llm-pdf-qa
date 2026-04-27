import asyncio
import json
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..audit import hash_value, log_audit

router = APIRouter(prefix="/api/v1")

M4_URL = os.getenv("M4_URL", "http://m4-rag:8000")


def _require_chat_perm(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    perms = user.get("permissions") or user.get("perm", [])
    if "chat.use" not in perms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing chat.use permission")
    return user


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    use_web_search: bool = False
    web_provider: Optional[str] = None


@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    user = _require_chat_perm(request)
    perms = user.get("permissions") or user.get("perm", [])
    if body.use_web_search and "web.search" not in perms:
        log_audit(
            "web_search.denied",
            user,
            request_id=getattr(request.state, "request_id", None),
            reason="missing_permission",
            provider=body.web_provider or "default",
            session_id=body.session_id,
            query_hash=hash_value(body.message),
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing web.search permission")
    if body.use_web_search:
        log_audit(
            "web_search.requested",
            user,
            request_id=getattr(request.state, "request_id", None),
            provider=body.web_provider or "default",
            session_id=body.session_id,
            query_hash=hash_value(body.message),
        )

    import httpx
    from ..clients.downstream import get_client

    async def sse_stream():
        client = get_client()
        payload = {
            "query": body.message,
            "session_id": body.session_id,
            "use_web": body.use_web_search,
            "web_provider": body.web_provider,
        }
        try:
            async with client.stream(
                "POST",
                f"{M4_URL}/rag/query",
                json=payload,
                params={"stream": "1"},
                timeout=httpx.Timeout(connect=3.0, read=30.0, write=10.0, pool=5.0),
            ) as resp:
                async for chunk in resp.aiter_text():
                    if chunk:
                        yield f"event: token\ndata: {json.dumps({'token': chunk, 'delta': chunk})}\n\n"
        except asyncio.CancelledError:
            # Client disconnected: propagate cancellation
            return
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(sse_stream(), media_type="text/event-stream")
