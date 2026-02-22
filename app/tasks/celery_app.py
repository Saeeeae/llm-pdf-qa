from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery("rag_worker")

celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "app.tasks.ingest_tasks.ingest_file": {"queue": "ingest"},
        "app.tasks.sync_tasks.run_daily_sync": {"queue": "sync"},
    },
    beat_schedule={
        "daily-sync": {
            "task": "app.tasks.sync_tasks.run_daily_sync",
            "schedule": crontab(
                hour=settings.sync_cron_hour,
                minute=settings.sync_cron_minute,
            ),
        },
    },
)

celery_app.autodiscover_tasks(["app.tasks"])
