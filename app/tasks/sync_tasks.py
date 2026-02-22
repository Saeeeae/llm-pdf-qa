import logging

from app.tasks.celery_app import celery_app
from app.pipeline.sync import run_sync

logger = logging.getLogger(__name__)


@celery_app.task
def run_daily_sync():
    """Scheduled task: scan watch directory and sync changes."""
    logger.info("Daily sync task started")
    stats = run_sync()
    logger.info("Daily sync task completed: %s", stats)
    return stats
