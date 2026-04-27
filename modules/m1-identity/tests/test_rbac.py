import pytest
from .conftest import make_token

pytestmark = pytest.mark.asyncio


async def test_list_users_admin(ctx):
    client, session, user, role = ctx
    token = make_token(user.id, "admin")
    r = await client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_list_users_no_perm(ctx):
    client, session, user, role = ctx
    token = make_token(user.id, "user", ["doc.read", "chat.use"])
    r = await client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


async def test_get_own_profile(ctx):
    client, session, user, role = ctx
    token = make_token(user.id, "user", ["doc.read", "chat.use"])
    r = await client.get(f"/users/{user.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["id"] == user.id


async def test_delete_user_requires_perm(ctx):
    client, session, user, role = ctx
    token = make_token(user.id, "user", ["doc.read", "chat.use"])
    r = await client.delete(f"/users/{user.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


async def test_delete_user_admin(ctx):
    client, session, user, role = ctx
    token = make_token(user.id, "admin")
    r = await client.delete(f"/users/{user.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204
