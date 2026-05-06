import os
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from .routers import ingest, sync

app = FastAPI(title="M2 Doc-to-MD", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m2-doc-to-md", "impl": os.getenv("MODULE_IMPL", "real")}


app.include_router(ingest.router)
app.include_router(sync.router)
app.mount("/metrics", make_asgi_app())
