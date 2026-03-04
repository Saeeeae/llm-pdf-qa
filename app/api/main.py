import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import documents, health, images, processing
from app.api.routes import auth, chat

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RAG-LLM API")
    yield
    logger.info("Shutting down RAG-LLM API")


app = FastAPI(
    title="사내 AI 어시스턴트 API",
    description="RAG 문서 전처리 + LLM 채팅 + 관리자 API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(processing.router, prefix="/api/v1/processing", tags=["Processing"])
app.include_router(images.router, prefix="/api/v1", tags=["Images"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
