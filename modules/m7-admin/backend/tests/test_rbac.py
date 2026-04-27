"""test_rbac.py — RBAC enforcement on admin endpoints."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_audit_log_no_token_rejected():
    r = client.get("/admin/audit-log")
    assert r.status_code in (401, 403)


def test_users_no_token_rejected():
    r = client.get("/admin/users")
    assert r.status_code in (401, 403)


def test_metrics_server_no_token_rejected():
    r = client.get("/admin/metrics/server")
    assert r.status_code in (401, 403)


def test_impersonate_no_token_rejected():
    r = client.post("/admin/users/some-uid/impersonate")
    assert r.status_code in (401, 403)


def test_csv_export_no_token_rejected():
    r = client.get("/admin/export/audit-log.csv")
    assert r.status_code in (401, 403)


def test_web_search_admin_no_token_rejected():
    r = client.get("/admin/web-search/providers")
    assert r.status_code in (401, 403)


def test_health_check_public():
    """Top-level /health is public (no auth required)."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_public():
    """/ready is public."""
    r = client.get("/ready")
    assert r.status_code == 200
