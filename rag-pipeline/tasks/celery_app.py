from celery import Celery
from shared.config import shared_settings

app = Celery("rag_pipeline")
app.conf.update(
    broker_url=shared_settings.celery_broker_url,
    result_backend=shared_settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    task_routes={"rag_pipeline.tasks.*": {"queue": "pipeline"}},
)
