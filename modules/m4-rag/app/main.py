import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.routers import rag
from app.session import aclose_pool as _close_session_pool

log = logging.getLogger("m4.startup")


async def _warm_models() -> None:
    """Eagerly load embedder + reranker so the first request doesn't pay the
    multi-second model-download / weight-load cost (which would also block the
    event loop, freezing concurrent requests)."""
    if os.getenv("WARM_MODELS_ON_STARTUP", "1") != "1":
        return
    try:
        from app.embed_client import QueryEmbedder
        await asyncio.to_thread(QueryEmbedder.get)
        log.info("query embedder warmed")
    except Exception as e:  # pragma: no cover — best-effort
        log.warning("query embedder warm-up failed: %s", e)

    if os.getenv("USE_RERANKER", "1") == "1":
        try:
            from app.reranker import Reranker
            await asyncio.to_thread(Reranker.get)
            log.info("reranker warmed")
        except Exception as e:  # pragma: no cover
            log.warning("reranker warm-up failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _warm_models()
    yield
    # Cleanly drain shared connection pools on shutdown.
    await _close_session_pool()


app = FastAPI(title="M4 RAG Engine", version="0.2.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "module": "m4-rag", "impl": os.getenv("MODULE_IMPL", "real")}


@app.get("/ready")
async def ready():
    errors = {}

    # DB ping
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        errors["db"] = str(exc)

    # vLLM ping (2 s timeout)
    vllm_url = os.getenv("VLLM_URL", "http://vllm:8000/v1")
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"{vllm_url}/models")
            r.raise_for_status()
    except Exception as exc:
        errors["vllm"] = str(exc)

    if errors:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "not_ready", "errors": errors})

    return {"status": "ready"}


app.include_router(rag.router)
