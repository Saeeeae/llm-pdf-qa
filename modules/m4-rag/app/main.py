import os

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.routers import rag

app = FastAPI(title="M4 RAG Engine", version="0.2.0")


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
