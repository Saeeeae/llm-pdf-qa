import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler

from rag_sync_monitor.sync.file_syncer import sync_directory
from rag_sync_monitor.trigger.pipeline_trigger import trigger_pending_documents

logger = logging.getLogger(__name__)


def run_file_sync() -> None:
    """Execute a single file-sync + pipeline-trigger cycle."""
    scan_path = os.getenv("SOURCE_SCAN_PATHS", "/mnt/nas/documents")
    dept_id = int(os.getenv("DEFAULT_DEPT_ID", "1"))
    role_id = int(os.getenv("DEFAULT_ROLE_ID", "3"))

    logger.info("Starting scheduled file sync: %s", scan_path)
    result = sync_directory(scan_path, dept_id=dept_id, role_id=role_id)

    if result.new_doc_ids:
        pipeline_url = os.getenv("PIPELINE_API_URL", "http://rag-pipeline:8001")
        trigger_pending_documents(pipeline_url)


def main() -> None:
    """Entry-point for the sync scheduler process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scheduler = BlockingScheduler()
    interval = int(os.getenv("SYNC_INTERVAL_MINUTES", "30"))
    scheduler.add_job(run_file_sync, "interval", minutes=interval, id="file_sync")
    logger.info("Scheduler started (interval=%dm)", interval)

    # Run once on startup
    run_file_sync()

    scheduler.start()


if __name__ == "__main__":
    main()
