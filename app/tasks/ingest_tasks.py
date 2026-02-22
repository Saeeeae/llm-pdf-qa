import logging

from app.tasks.celery_app import celery_app
from app.pipeline.ingest import ingest_document

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_file(self, file_path: str, folder_id: int | None = None):
    """Async task to ingest a single document file."""
    try:
        doc_id = ingest_document(file_path, folder_id=folder_id)
        logger.info("Task completed: ingested %s -> doc_id=%d", file_path, doc_id)
        return {"status": "ok", "doc_id": doc_id, "file_path": file_path}
    except Exception as exc:
        logger.error("Task failed for %s (attempt %d): %s", file_path, self.request.retries + 1, exc)
        self.retry(exc=exc)
