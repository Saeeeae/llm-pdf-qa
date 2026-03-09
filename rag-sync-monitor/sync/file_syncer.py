import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from shared.db import get_session
from shared.models.orm import Document, SyncLog

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls", ".pptx",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff",
}


@dataclass
class SyncResult:
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    new_doc_ids: list[int] = field(default_factory=list)


def compute_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def sync_directory(scan_path: str, dept_id: int = 1, role_id: int = 3) -> SyncResult:
    """Sync a local directory (NFS mount) with the document database.

    Scans the filesystem for supported files, computes SHA-256 checksums,
    compares with the ``document`` table, and writes a summary to ``sync_logs``.
    """
    result = SyncResult()

    # Start sync log
    with get_session() as session:
        sync_log = SyncLog(sync_type="file", status="running")
        session.add(sync_log)
        session.flush()
        log_id = sync_log.id

    try:
        # Scan filesystem
        scanned: dict[str, dict] = {}
        base = Path(scan_path)
        if not base.is_dir():
            logger.warning("Scan path not found: %s", scan_path)
            return result

        for root, _, files in os.walk(scan_path):
            for fname in files:
                fpath = Path(root) / fname
                if not fpath.is_file():
                    continue
                ext = fpath.suffix.lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                full_path = str(fpath)
                scanned[full_path] = {
                    "path": full_path,
                    "name": fpath.name,
                    "ext": ext.lstrip("."),
                    "size": fpath.stat().st_size,
                    "hash": compute_hash(full_path),
                }

        # Compare with DB
        with get_session() as session:
            existing = session.query(Document).all()
            db_by_path: dict[str, Document] = {doc.path: doc for doc in existing}
            db_by_hash: set[str] = {doc.hash for doc in existing}

            # Find added files
            for path, meta in scanned.items():
                if path not in db_by_path and meta["hash"] not in db_by_hash:
                    doc = Document(
                        file_name=meta["name"],
                        path=meta["path"],
                        type=meta["ext"],
                        hash=meta["hash"],
                        size=meta["size"],
                        dept_id=dept_id,
                        role_id=role_id,
                        status="pending",
                    )
                    session.add(doc)
                    session.flush()
                    result.new_doc_ids.append(doc.doc_id)
                    result.files_added += 1

            # Find modified files (same path, different hash)
            for path, meta in scanned.items():
                if path in db_by_path:
                    doc = db_by_path[path]
                    if doc.hash != meta["hash"]:
                        doc.hash = meta["hash"]
                        doc.size = meta["size"]
                        doc.status = "pending"
                        doc.updated_at = datetime.now(timezone.utc)
                        result.new_doc_ids.append(doc.doc_id)
                        result.files_modified += 1

            # Find deleted files (in DB but not on disk)
            for path, doc in db_by_path.items():
                if path not in scanned:
                    doc.status = "deleted"
                    doc.error_msg = "File removed from source"
                    doc.updated_at = datetime.now(timezone.utc)
                    result.files_deleted += 1

        # Update sync log with success
        with get_session() as session:
            log = session.query(SyncLog).filter(SyncLog.id == log_id).first()
            if log:
                log.status = "success"
                log.finished_at = datetime.now(timezone.utc)
                log.files_added = result.files_added
                log.files_modified = result.files_modified
                log.files_deleted = result.files_deleted

        logger.info(
            "Sync complete: +%d ~%d -%d",
            result.files_added, result.files_modified, result.files_deleted,
        )

    except Exception as e:
        with get_session() as session:
            log = session.query(SyncLog).filter(SyncLog.id == log_id).first()
            if log:
                log.status = "failed"
                log.finished_at = datetime.now(timezone.utc)
                log.error_message = str(e)[:1000]
        logger.error("Sync failed: %s", e)
        raise

    return result
