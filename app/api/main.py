import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import documents, processing, health
from app.db.qdrant import QdrantManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure Qdrant collection exists
    logger.info("Starting RAG Preprocessing API")
    QdrantManager()
    yield
    logger.info("Shutting down RAG Preprocessing API")


app = FastAPI(
    title="RAG Document Preprocessing API",
    description="문서 OCR, Chunking, Embedding 처리 및 DB/Vector DB 관리 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router, tags=["Health"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(processing.router, prefix="/api/v1/processing", tags=["Processing"])
