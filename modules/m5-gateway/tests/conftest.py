import os
os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ["M1_URL"] = "http://mock-m1"
os.environ["M4_URL"] = "http://mock-m4"
os.environ["DOWNSTREAM_FALLBACK"] = "mock"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from jose import jwt

from app.main import app


def make_token(sub: str = "1", role: str = "user", perms: list = None) -> str:
    from datetime import datetime, timedelta, timezone
    if perms is None:
        perms = ["chat.use", "doc.read"]
    payload = {
        "sub": sub,
        "role": role,
        "perm": perms,
        "permissions": perms,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


@pytest_asyncio.fixture()
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
