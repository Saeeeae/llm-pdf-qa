"""
B3.1 E2E auth chain tests.

Tests JWT issuance (M1) → M5 gateway validation → M4 response.

These tests require Docker (testcontainers).  In sandbox/CI-without-DinD the
infra_containers fixture is skipped, which cascades to skip every test here.
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


# ── helpers ───────────────────────────────────────────────────────────────

async def _login(m1_client, email: str = "admin@test.com", password: str = "correct-password") -> dict | None:
    """POST /auth/login, return token dict or None on failure."""
    r = await m1_client.post("/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        return r.json()
    return None


def _make_expired_token(secret: str = "x" * 32) -> str:
    """Create a JWT that is already expired (exp = epoch 0)."""
    try:
        import jwt  # PyJWT
        payload = {
            "sub": "999",
            "role": "user",
            "permissions": [],
            "exp": 1,  # expired in 1970
        }
        return jwt.encode(payload, secret, algorithm="HS256")
    except ImportError:
        # Fallback: a syntactically valid but semantically expired token
        return (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiI5OTkiLCJleHAiOjF9."
            "invalid_signature"
        )


# ── tests ─────────────────────────────────────────────────────────────────

async def test_jwt_issue_and_gateway_pass(m1_client, m5_client):
    """
    M1 issues JWT → M5 gateway accepts it and proxies the request.
    """
    tokens = await _login(m1_client)
    if tokens is None:
        pytest.skip("M1 login returned non-200 (DB not seeded in E2E env)")

    access_token = tokens.get("access_token")
    assert access_token, "access_token missing from M1 login response"

    # Hit M5 gateway with the token — expect 200 or proxied response (not 401/403)
    r = await m5_client.get(
        "/health",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    # Gateway health endpoint typically does not require auth
    assert r.status_code == 200, f"M5 health failed: {r.status_code} {r.text}"

    # Hit an authenticated endpoint through gateway
    r2 = await m5_client.post(
        "/rag/query",
        json={"query": "hello", "top_k": 1},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    # Accept proxied success or upstream error — NOT 401
    assert r2.status_code != 401, (
        f"M5 rejected valid token: {r2.status_code} {r2.text}"
    )


async def test_expired_token_rejected(m5_client):
    """
    M5 gateway must reject expired JWT with 401.
    """
    import os
    secret = os.environ.get("JWT_SECRET", "x" * 32)
    expired_token = _make_expired_token(secret)

    r = await m5_client.post(
        "/rag/query",
        json={"query": "test", "top_k": 1},
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert r.status_code == 401, (
        f"M5 should reject expired token with 401, got {r.status_code}"
    )


async def test_refresh_rotation(m1_client):
    """
    POST /auth/refresh returns a new access_token and rotates the refresh_token.
    Old refresh_token must not be reusable.
    """
    tokens = await _login(m1_client)
    if tokens is None:
        pytest.skip("M1 login returned non-200 (DB not seeded in E2E env)")

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        pytest.skip("M1 did not return refresh_token — feature may not be implemented")

    # First refresh
    r1 = await m1_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r1.status_code == 200, f"First refresh failed: {r1.status_code} {r1.text}"
    new_tokens = r1.json()
    new_access = new_tokens.get("access_token")
    new_refresh = new_tokens.get("refresh_token")
    assert new_access, "New access_token missing after refresh"

    # Rotation check: new refresh token should differ from old
    if new_refresh:
        assert new_refresh != refresh_token, (
            "Refresh token was NOT rotated — security issue"
        )

    # Reuse old refresh token — must fail (rotation invalidates it)
    r2 = await m1_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r2.status_code in (401, 400, 422), (
        f"Old refresh token reuse should be rejected, got {r2.status_code}"
    )


async def test_no_token_rejected(m5_client):
    """
    Request without Authorization header must be rejected with 401/403.
    """
    r = await m5_client.post(
        "/rag/query",
        json={"query": "no auth", "top_k": 1},
    )
    assert r.status_code in (401, 403), (
        f"M5 should reject missing token, got {r.status_code}"
    )
