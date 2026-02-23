import logging
import os
from datetime import datetime, timezone

from app.config import settings
from app.db.models import Document, DocChunk, SystemJob
from app.db.postgres import get_session
from app.db.qdrant import QdrantManager
from app.pipeline.ingest import compute_file_hash
from app.pipeline.ingest import ingest_document
from app.pipeline.scanner import scan_files

logger = logging.getLogger(__name__)


def scan_directory(watch_dir: str) -> dict[str, int]:
    """Scan directory recursively. Returns {absolute_path: file_size_bytes}."""
    result = scan_files(watch_dir, recursive=True, compute_hash=False)
    return {f.path: f.size for f in result.files}


def run_sync() -> dict:
    """Compare filesystem vs DB. Process new/modified/deleted files.

    Returns summary stats dict.
    """
    watch_dir = settings.doc_watch_dir
    logger.info("Starting sync for: %s", watch_dir)

    if not os.path.isdir(watch_dir):
        logger.error("Watch directory does not exist: %s", watch_dir)
        return {"error": f"Directory not found: {watch_dir}"}

    disk_files = scan_directory(watch_dir)
    logger.info("Found %d files on disk", len(disk_files))
    qdrant = QdrantManager()

    stats = {"new": 0, "modified": 0, "deleted": 0, "unchanged": 0, "errors": 0}

    with get_session() as session:
        # Create job record
        job = SystemJob(
            job_name="daily_sync",
            job_type="nas_sync",
            status="running",
            last_run_at=datetime.now(timezone.utc),
        )
        session.add(job)
        session.flush()

        # Get all active documents from DB
        db_docs = (
            session.query(Document)
            .filter(Document.status.in_(["indexed", "pending", "processing", "failed"]))
            .all()
        )
        db_map: dict[str, Document] = {doc.path: doc for doc in db_docs}

        # 1. Process NEW and MODIFIED files
        for abs_path, file_size in disk_files.items():
            if abs_path not in db_map:
                # NEW file
                try:
                    ingest_document(abs_path)
                    stats["new"] += 1
                    logger.info("New file ingested: %s", abs_path)
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Error ingesting new file %s: %s", abs_path, e)
            elif db_map[abs_path].size != file_size:
                # MODIFIED file (size changed) - delete old data, re-ingest
                old_doc = db_map[abs_path]
                try:
                    _delete_document_data(session, old_doc, qdrant=qdrant)
                    ingest_document(abs_path)
                    stats["modified"] += 1
                    logger.info("Modified file re-ingested (size changed): %s", abs_path)
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Error re-ingesting modified file %s: %s", abs_path, e)
            else:
                # Same path and same size: compute hash only now.
                try:
                    current_hash = compute_file_hash(abs_path)
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Error hashing file %s: %s", abs_path, e)
                    continue

                if db_map[abs_path].hash != current_hash:
                    old_doc = db_map[abs_path]
                    try:
                        _delete_document_data(session, old_doc, qdrant=qdrant)
                        ingest_document(abs_path)
                        stats["modified"] += 1
                        logger.info("Modified file re-ingested (same size): %s", abs_path)
                    except Exception as e:
                        stats["errors"] += 1
                        logger.error("Error re-ingesting modified file %s: %s", abs_path, e)
                else:
                    stats["unchanged"] += 1

        # 2. Find DELETED files (in DB but not on disk)
        for abs_path, doc in db_map.items():
            if abs_path not in disk_files:
                try:
                    _delete_document_data(session, doc, qdrant=qdrant)
                    stats["deleted"] += 1
                    logger.info("Deleted file cleaned up: %s", abs_path)
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Error cleaning up deleted file %s: %s", abs_path, e)

        # Update job status
        job.status = "completed" if stats["errors"] == 0 else "completed_with_errors"
        job.last_error = f"Stats: {stats}" if stats["errors"] > 0 else None

    logger.info("Sync completed: %s", stats)
    return stats


def _delete_document_data(session, doc: Document, qdrant: QdrantManager | None = None):
    """Remove chunks from Qdrant and delete document record."""
    try:
        (qdrant or QdrantManager()).delete_by_doc_id(doc.doc_id)
    except Exception as e:
        logger.warning("Failed to delete vectors from Qdrant for doc_id=%d: %s", doc.doc_id, e)

    session.query(DocChunk).filter(DocChunk.doc_id == doc.doc_id).delete()
    session.delete(doc)
    logger.info("Deleted document data: doc_id=%d, file=%s", doc.doc_id, doc.file_name)
