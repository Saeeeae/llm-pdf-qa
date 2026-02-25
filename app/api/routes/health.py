import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.postgres import engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health_check():
    """전체 시스템 상태 확인."""
    status = {"status": "ok", "services": {}}

    # PostgreSQL + pgvector
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            # pgvector extension 확인
            result = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
            row = result.fetchone()
            status["services"]["postgres"] = f"healthy (pgvector {row[0]})" if row else "healthy (pgvector not installed)"
    except Exception as e:
        status["services"]["postgres"] = f"unhealthy: {e}"
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
