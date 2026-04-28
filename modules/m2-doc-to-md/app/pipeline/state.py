import json
import os
from pathlib import Path

_DEFAULT_STATE_DIR = Path(__file__).resolve().parents[2]
STATE_DIR = Path(os.getenv("M2_STATE_DIR", _DEFAULT_STATE_DIR))
STATE_FILE = STATE_DIR / ".pipeline_state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"files": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)
