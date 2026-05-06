"""Orchestrates m2's in-house DB sync: pull both upstreams → JSON state."""
import logging
from datetime import datetime, timezone
from typing import Any

from .mysql_client import (
    fetch_files,
    fetch_folder_permissions,
    make_file_engine,
    make_hr_engine,
)
from .state import append_history, load_state, save_state

log = logging.getLogger(__name__)


def _file_key(row: dict) -> str:
    """Identifier for dedup. FilePath should be unique per file in F0_00001_F."""
    return str(row.get("FilePath") or row.get("FileName") or "")


async def run_sync() -> dict[str, Any]:
    """Pull files + folder ACLs and persist. Returns the run summary dict."""
    started = datetime.now(timezone.utc)
    state = load_state()
    status = "success"
    error_text: str | None = None
    files_count = 0
    perms_count = 0

    file_engine = make_file_engine()
    hr_engine = make_hr_engine()
    try:
        file_rows = await fetch_files(file_engine)
        folder_perms = await fetch_folder_permissions(hr_engine)

        files_dict: dict[str, dict] = {}
        for row in file_rows:
            key = _file_key(row)
            if not key:
                continue
            files_dict[key] = row

        state["files"] = files_dict
        state["folder_perms"] = folder_perms
        files_count = len(files_dict)
        perms_count = len(folder_perms)
        log.info("m2 sync ok: files=%d folder_perms=%d", files_count, perms_count)
    except Exception as e:
        status = "error"
        error_text = str(e)
        log.exception("m2 sync failed")
    finally:
        await file_engine.dispose()
        await hr_engine.dispose()

    finished = datetime.now(timezone.utc)
    run = {
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "status": status,
        "files": files_count,
        "folder_perms": perms_count,
        "error": error_text,
        "duration_ms": (finished - started).total_seconds() * 1000,
    }
    append_history(state, run)
    save_state(state)
    return run
