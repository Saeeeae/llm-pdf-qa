import logging

from fastapi import APIRouter
from qdrant_client import QdrantClient
from sqlalchemy import text

from app.config import settings
from app.db.postgres import engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health_check():
    """전체 시스템 상태 확인."""
    status = {"status": "ok", "services": {}}

    # PostgreSQL
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["services"]["postgres"] = "healthy"
    except Exception as e:
        status["services"]["postgres"] = f"unhealthy: {e}"
        status["status"] = "degraded"

    # Qdrant
    try:
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=5)
        client.get_collections()
        status["services"]["qdrant"] = "healthy"
    except Exception as e:
        status["services"]["qdrant"] = f"unhealthy: {e}"
        status["status"] = "degraded"

    # Redis
    try:
        import redis
        r = redis.Redis.from_url(settings.celery_broker_url, socket_timeout=3)
        r.ping()
        status["services"]["redis"] = "healthy"
    except Exception as e:
        status["services"]["redis"] = f"unhealthy: {e}"
        status["status"] = "degraded"

    return status
