import hashlib
import logging
import os
from pathlib import Path

SUPPORTED_EXT = {".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".hwp", ".hwpx"}

logger = logging.getLogger("m2.scanner")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(source_dir: Path, state: dict) -> dict:
    """Diff filesystem vs state. Returns {new, modified, deleted, unchanged}."""
    prev = state.get("files", {})
    current = {}
    source_real = source_dir.resolve()
    for root, _, files in os.walk(source_dir, followlinks=False):
        for name in files:
            p = Path(root) / name
            if p.is_symlink():
                logger.warning("skip symlink %s", p)
                continue
            try:
                real = p.resolve()
            except OSError:
                continue
            if not str(real).startswith(str(source_real)):
                logger.warning("path escape %s", p)
                continue
            if Path(name).suffix.lower() not in SUPPORTED_EXT:
                continue
            rel = str(p.relative_to(source_dir))
            current[rel] = {
                "hash": _sha256(p),
                "mtime": p.stat().st_mtime,
                "abs": str(p),
            }
    new, modified, unchanged = [], [], []
    for rel, meta in current.items():
        if rel not in prev:
            new.append(rel)
        elif prev[rel].get("hash") != meta["hash"]:
            modified.append(rel)
        else:
            unchanged.append(rel)
    deleted = [rel for rel in prev if rel not in current]
    return {
        "new": new,
        "modified": modified,
        "deleted": deleted,
        "unchanged": unchanged,
        "current": current,
    }
