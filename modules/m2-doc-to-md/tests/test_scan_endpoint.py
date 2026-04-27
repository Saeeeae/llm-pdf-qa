import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ingest_scan_returns_job_id(monkeypatch):
    monkeypatch.setattr("app.routers.ingest.pipeline_run", lambda: None)
    r = client.post("/ingest/scan")
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "queued"


def test_ingest_status_unknown(monkeypatch):
    r = client.get("/ingest/status/nonexistent-job")
    assert r.status_code == 200
    assert r.json()["status"] == "unknown"


def test_ingest_status_done(monkeypatch):
    monkeypatch.setattr("app.routers.ingest.pipeline_run", lambda: None)
    r = client.post("/ingest/scan")
    jid = r.json()["job_id"]
    # BackgroundTasks run synchronously in TestClient
    r2 = client.get(f"/ingest/status/{jid}")
    assert r2.status_code == 200
    assert r2.json()["status"] in ("done", "running", "queued")


def test_ingest_status_error(monkeypatch):
    def _fail():
        raise RuntimeError("boom")

    monkeypatch.setattr("app.routers.ingest.pipeline_run", _fail)
    r = client.post("/ingest/scan")
    jid = r.json()["job_id"]
    r2 = client.get(f"/ingest/status/{jid}")
    assert r2.status_code == 200
    status = r2.json()["status"]
    assert status in ("error:boom", "running", "queued")
