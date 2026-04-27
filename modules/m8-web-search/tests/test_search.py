from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_curated_search_schema():
    # Mock SSRF check so DNS-less test environments don't block public URLs
    with patch("app.policy._is_blocked_host", return_value=False):
        r = client.post(
            "/web-search/search",
            json={"query": "p53 clinical trial", "provider": "curated", "max_results": 2},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["blocked"] is False
    assert data["provider"] == "curated"
    assert len(data["results"]) == 2
    assert data["results"][0]["title"]
    assert data["citations"][0]["url"].startswith("https://")


def test_blocked_query_does_not_return_results():
    r = client.post(
        "/web-search/search",
        json={"query": "search /data/private.docx", "provider": "curated"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["blocked"] is True
    assert data["results"] == []
    assert data["blocked_reason"] == "query_contains_sensitive_data"


def test_ssrf_localhost_blocked():
    """Direct calls to localhost/private IPs are rejected."""
    from app.policy import is_url_allowed
    ok, reason = is_url_allowed("http://localhost/admin")
    assert ok is False
    assert reason == "ssrf_blocked"

    ok, reason = is_url_allowed("http://127.0.0.1/secret")
    assert ok is False
    assert reason == "ssrf_blocked"

    ok, reason = is_url_allowed("http://169.254.169.254/latest/meta-data/")
    assert ok is False
    assert reason == "ssrf_blocked"


def test_provider_listing():
    r = client.get("/web-search/providers")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()["providers"]}
    assert {"curated", "brave", "exa", "searxng", "mock"}.issubset(names)
