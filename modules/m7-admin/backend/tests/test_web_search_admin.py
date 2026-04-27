from unittest.mock import AsyncMock, patch

import httpx
import pytest
from jose import jwt

from app.main import app


def _token(perms):
    import os
    from datetime import datetime, timedelta, timezone

    return jwt.encode(
        {
            "sub": "admin-1",
            "permissions": perms,
            "perm": perms,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_web_search_providers_proxies_m8():
    from httpx import ASGITransport, AsyncClient

    response = httpx.Response(
        200,
        json={"providers": [{"name": "curated", "configured": True}]},
        request=httpx.Request("GET", "http://m8/web-search/providers"),
    )
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(
                "/admin/web-search/providers",
                headers={"Authorization": f"Bearer {_token(['admin.read'])}"},
            )
    assert r.status_code == 200
    assert r.json()["providers"][0]["name"] == "curated"


@pytest.mark.asyncio
async def test_web_search_audit_requires_audit_permission():
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(
            "/admin/web-search/audit-summary",
            headers={"Authorization": f"Bearer {_token(['admin.read'])}"},
        )
    assert r.status_code == 403
