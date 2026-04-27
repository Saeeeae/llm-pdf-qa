from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["module"] == "m8-web-search"


def test_ready():
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
