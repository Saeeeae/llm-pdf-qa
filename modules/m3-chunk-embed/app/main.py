import os
from fastapi import FastAPI
from sqlalchemy import text
from app.db import engine
from app.routers import chunk_embed

app = FastAPI(title="M3 Chunk/Embed", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m3-chunk-embed", "impl": os.getenv("MODULE_IMPL", "real")}


@app.get("/ready")
async def ready():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(503, detail=f"db unavailable: {exc}")


app.include_router(chunk_embed.router)
