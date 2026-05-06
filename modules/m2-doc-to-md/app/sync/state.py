"""JSON-file persistence for m2's in-house DB sync state.

Stored alongside the existing pipeline state. Schema:
{
  "last_run": {"started_at": "...", "finished_at": "...", "status": "...",
               "files": <int>, "folder_perms": <int>, "error": <str|null>},
  "history": [ ... up to LOG_BACKUP_COUNT entries ... ],
  "files": { "<file_id>": { "FileName": ..., "FilePath": ..., ... } },
  "folder_perms": { "<folder>": ["user_id", ...] }
}

Path resolution:
- M2_STATE_DIR env (recommended in docker — bind-mounted from data/db/m2-state/)
- Falls back to module root for local dev runs
"""
import json
import os
from pathlib import Path
from typing import Any

_STATE_DIR_ENV = os.getenv("M2_STATE_DIR")
if _STATE_DIR_ENV:
    STATE_FILE = Path(_STATE_DIR_ENV) / "sync_state.json"
else:
    STATE_FILE = Path(__file__).resolve().parents[2] / ".sync_state.json"

_HISTORY_LIMIT = int(os.getenv("M2_SYNC_HISTORY_LIMIT", "50"))


def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_run": None, "history": [], "files": {}, "folder_perms": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    tmp.replace(STATE_FILE)


def append_history(state: dict[str, Any], run: dict[str, Any]) -> None:
    state["last_run"] = run
    history = state.setdefault("history", [])
    history.insert(0, run)
    del history[_HISTORY_LIMIT:]
