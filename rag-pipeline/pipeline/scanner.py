import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from shared.db import get_session
from shared.models.orm import Document

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xls", ".pptx",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff",
}


@dataclass
class ScanDiff:
    added: list[dict] = field(default_factory=list)
    modified: list[dict] = field(default_factory=list)
    deleted: list[int] = field(default_factory=list)


def compute_file_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def scan_directory(directory: str, recursive: bool = True) -> list[dict]:
    files = []
    base = Path(directory)
    if not base.is_dir():
        logger.warning("Directory not found: %s", directory)
        return files

    walker = os.walk(directory) if recursive else [(directory, [], os.listdir(directory))]
    for root, _, filenames in walker:
        for fname in filenames:
            fpath = Path(root) / fname
            if not fpath.is_file():
                continue
            ext = fpath.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            files.append({
                "path": str(fpath),
                "name": fpath.name,
                "ext": ext.lstrip("."),
                "size": fpath.stat().st_size,
                "hash": compute_file_hash(str(fpath)),
            })
    return files


def diff_with_db(scanned_files: list[dict]) -> ScanDiff:
    diff = ScanDiff()
    with get_session() as session:
        existing = session.query(Document).filter(Document.status != 'failed').all()
        db_by_path = {doc.path: doc for doc in existing}
        db_by_hash = {doc.hash: doc for doc in existing}

    scanned_paths = set()
    for f in scanned_files:
        scanned_paths.add(f["path"])
        if f["path"] in db_by_path:
            doc = db_by_path[f["path"]]
            if doc.hash != f["hash"]:
                diff.modified.append({**f, "doc_id": doc.doc_id})
        elif f["hash"] not in db_by_hash:
            diff.added.append(f)

    for path, doc in db_by_path.items():
        if path not in scanned_paths:
            diff.deleted.append(doc.doc_id)

    logger.info("Scan diff: +%d ~%d -%d", len(diff.added), len(diff.modified), len(diff.deleted))
    return diff
