from rag_pipeline.tasks.celery_app import app
from rag_pipeline.pipeline.orchestrator import process_document


@app.task(name="rag_pipeline.tasks.process_document", bind=True, max_retries=2)
def process_document_task(self, doc_id: int):
    try:
        process_document(doc_id)
    except Exception as exc:
        self.retry(exc=exc, countdown=30)


@app.task(name="rag_pipeline.tasks.process_batch")
def process_batch_task(doc_ids: list[int]):
    for doc_id in doc_ids:
        process_document_task.delay(doc_id)
