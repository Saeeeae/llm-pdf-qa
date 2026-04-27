import os

from fastapi import FastAPI

from .routers import search

app = FastAPI(title="M8 Web Search", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m8-web-search", "impl": os.getenv("MODULE_IMPL", "real")}


@app.get("/ready")
def ready():
    return {"status": "ok", "default_provider": os.getenv("M8_DEFAULT_PROVIDER", "curated")}


app.include_router(search.router)
