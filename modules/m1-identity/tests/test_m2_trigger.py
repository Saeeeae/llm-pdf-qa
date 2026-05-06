"""m1 → m2 ordered sync trigger contract.

Verifies:
- trigger_m2 hits the URL with the internal token header
- trigger_m2 swallows network/HTTP errors (m1 sync still marked success)
- trigger_m2 is a no-op when M2_INTERNAL_SYNC_URL is unset
"""
import os
os.environ["TEST_MODE"] = "1"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-chars-long"

import pytest


@pytest.mark.asyncio
async def test_trigger_m2_posts_with_token(monkeypatch):
    monkeypatch.setenv("M2_INTERNAL_SYNC_URL", "http://m2.test/internal/sync/mysql")
    monkeypatch.setenv("INTERNAL_SYNC_TOKEN", "shared-secret-xyz")

    captured: dict = {}

    class FakeResponse:
        status_code = 202
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    from app.sync.notify import trigger_m2
    await trigger_m2()

    assert captured["url"] == "http://m2.test/internal/sync/mysql"
    assert captured["headers"]["X-Internal-Token"] == "shared-secret-xyz"
    assert captured["json"]["source"] == "m1-scheduler"


@pytest.mark.asyncio
async def test_trigger_m2_swallows_errors(monkeypatch):
    """m2 unreachable must NOT raise — m1's sync_run already committed success."""
    monkeypatch.setenv("M2_INTERNAL_SYNC_URL", "http://unreachable.test/x")
    monkeypatch.setenv("INTERNAL_SYNC_TOKEN", "tok")

    class BoomClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw):
            raise RuntimeError("connection refused")

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", BoomClient)

    from app.sync.notify import trigger_m2
    await trigger_m2()  # must not raise


@pytest.mark.asyncio
async def test_trigger_m2_noop_without_url(monkeypatch):
    monkeypatch.delenv("M2_INTERNAL_SYNC_URL", raising=False)

    called = []

    class TrackingClient:
        def __init__(self, *a, **kw): called.append(1)
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw): called.append("post")

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", TrackingClient)

    from app.sync.notify import trigger_m2
    await trigger_m2()
    assert called == []  # no client constructed, no post issued
