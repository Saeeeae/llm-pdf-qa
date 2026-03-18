from rag_pipeline.tasks.celery_app import app
from rag_pipeline.pipeline.orchestrator import process_document


@app.task(name="rag_pipeline.tasks.process_document", bind=True, max_retries=2)
def process_document_task(self, doc_id: int):
    try:
        process_document(doc_id)
    except ValueError as exc:
        if str(exc).startswith("Document ") and str(exc).endswith(" not found"):
            app.log.get_default_logger().warning(
                "Skipping stale pipeline task for missing document doc_id=%s: %s",
                doc_id,
                exc,
            )
            return
        self.retry(exc=exc, countdown=30)
    except Exception as exc:
        self.retry(exc=exc, countdown=30)


@app.task(name="rag_pipeline.tasks.process_batch")
def process_batch_task(doc_ids: list[int]):
    for doc_id in doc_ids:
        process_document_task.delay(doc_id)
