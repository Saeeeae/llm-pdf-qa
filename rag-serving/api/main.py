import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from rag_serving.api.routers import auth, chat, admin
from shared.middleware import RequestLoggingMiddleware

_BASE_DIR = Path(os.path.abspath(__file__)).resolve().parent.parent  # rag_serving/
_ADMIN_DIR = str(_BASE_DIR / "admin")

app = FastAPI(title="RAG Serving API", version="2.0")

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])

if os.path.isdir(_ADMIN_DIR) and any(f.endswith(".html") for f in os.listdir(_ADMIN_DIR)):
    app.mount("/admin", StaticFiles(directory=_ADMIN_DIR, html=True), name="admin")


@app.get("/health")
def health():
    return {"status": "ok"}
