"""GET /admin/health endpoint tests."""
import os
os.environ["TEST_MODE"] = "1"
os.environ.setdefault("JWT_SECRET", "x" * 32)

import pytest
from .conftest import make_token


@pytest.mark.asyncio
async def test_admin_health_unauthorized(client):
    r = await client.get("/admin/health")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_health_forbidden_without_admin_read(client, db_with_user):
    _, user, _ = db_with_user
    token = make_token(user.id, perms=["doc.read"])  # no admin.read
    r = await client.get("/admin/health", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_health_returns_counts(client, db_with_user):
    _, user, role = db_with_user
    token = make_token(user.id)
    r = await client.get("/admin/health", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["users"]["total"] >= 1
    assert body["users"]["active"] >= 1
    assert "admin" in body["users"]["by_role"]
    assert body["users"]["by_role"]["admin"] >= 1
    assert body["roles"]["total"] >= 1
    assert "departments" in body
    # last_sync_run is null until a sync has run
    assert "last_sync_run" in body


@pytest.mark.asyncio
async def test_admin_health_includes_last_sync_when_present(client, db_with_user):
    """A SyncRun row is summarised in last_sync_run with age_seconds."""
    from datetime import datetime, timedelta, timezone
    from app.models import SyncRun
    from app.db import AsyncSessionLocal

    _, user, _ = db_with_user
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    finished = datetime.now(timezone.utc) - timedelta(minutes=4)
    async with AsyncSessionLocal() as s:
        s.add(SyncRun(
            started_at=started,
            finished_at=finished,
            status="success",
            report={"users_added": 12},
        ))
        await s.commit()

    token = make_token(user.id)
    r = await client.get("/admin/health", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    last = body["last_sync_run"]
    assert last is not None
    assert last["status"] == "success"
    assert last["report"] == {"users_added": 12}
    assert last["age_seconds"] is not None
    assert 200 < last["age_seconds"] < 400  # ~4 minutes
