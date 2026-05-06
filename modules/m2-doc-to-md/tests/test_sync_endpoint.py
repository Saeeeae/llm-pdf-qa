"""m2 internal sync endpoint contract.

Verifies:
- token-gated (401 without/with wrong token, 202 with right token)
- BackgroundTasks scheduled exactly once per accepted call
- /status returns persisted state shape
"""
import os
os.environ["INTERNAL_SYNC_TOKEN"] = "test-token-xyz"

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sync import state as state_mod


client = TestClient(app)


def test_trigger_rejects_missing_token():
    r = client.post("/internal/sync/mysql")
    assert r.status_code == 401


def test_trigger_rejects_wrong_token():
    r = client.post("/internal/sync/mysql", headers={"X-Internal-Token": "nope"})
    assert r.status_code == 401


def test_trigger_accepts_correct_token(monkeypatch):
    # Stub out the actual sync work so the test doesn't try to open MySQL
    called = []
    async def fake_locked():
        called.append(1)
    monkeypatch.setattr("app.routers.sync._run_locked", fake_locked)

    r = client.post("/internal/sync/mysql", headers={"X-Internal-Token": "test-token-xyz"})
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"
    assert called == [1]  # background task ran exactly once


def test_status_returns_state(tmp_path, monkeypatch):
    state_file = tmp_path / ".sync_state.json"
    state_file.write_text(json.dumps({
        "last_run": {"status": "success", "files": 12},
        "history": [{"status": "success", "files": 12}],
        "files": {"a": {}, "b": {}},
        "folder_perms": {"/dept/eng": ["u1", "u2"]},
    }))
    monkeypatch.setattr(state_mod, "STATE_FILE", state_file)

    r = client.get("/internal/sync/mysql/status", headers={"X-Internal-Token": "test-token-xyz"})
    assert r.status_code == 200
    body = r.json()
    assert body["last_run"]["status"] == "success"
    assert body["files_cached"] == 2
    assert body["folder_perms_cached"] == 1
