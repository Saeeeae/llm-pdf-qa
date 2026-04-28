"""B2.4 — Session history tests using fakeredis."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_redis_mock(existing: list[str] | None = None):
    """Build a minimal async Redis mock with lrange/lpush/ltrim/expire/pipeline."""
    r = AsyncMock()
    store: list[str] = list(existing or [])

    async def lrange(key, start, stop):
        return store[start:stop + 1]

    r.lrange = AsyncMock(side_effect=lrange)
    r.aclose = AsyncMock()

    # Pipeline mock
    pipe = AsyncMock()
    pipe.lpush = MagicMock(return_value=pipe)
    pipe.ltrim = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)

    async def pipe_execute():
        return []

    pipe.execute = AsyncMock(side_effect=pipe_execute)
    r.pipeline = MagicMock(return_value=pipe)

    return r, store, pipe


@pytest.mark.asyncio
async def test_get_history_empty():
    """get_history returns [] when no data in Redis."""
    r, _, _ = _make_redis_mock([])
    with patch("app.session._client", return_value=r):
        from app.session import get_history
        result = await get_history("sess-1")
    assert result == []


@pytest.mark.asyncio
async def test_get_history_reverses_order():
    """get_history reverses lrange result (lpush order → chronological)."""
    items = [
        json.dumps({"role": "assistant", "content": "hi"}),
        json.dumps({"role": "user", "content": "hello"}),
    ]
    r, _, _ = _make_redis_mock(items)
    with patch("app.session._client", return_value=r):
        from app.session import get_history
        result = await get_history("sess-1")
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_add_turn_uses_pipeline():
    """add_turn calls lpush twice and sets TTL via pipeline."""
    r, _, pipe = _make_redis_mock()
    with patch("app.session._client", return_value=r):
        from app.session import add_turn
        await add_turn("sess-2", "user question", "assistant answer")

    assert pipe.lpush.call_count == 2
    pipe.ltrim.assert_called_once()
    pipe.expire.assert_called_once()
    pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_turn_correct_content():
    """add_turn pushes user before assistant (lpush reverses list)."""
    pushed = []
    r, _, pipe = _make_redis_mock()

    def capture_lpush(key, value):
        pushed.append(json.loads(value))
        return pipe

    pipe.lpush = MagicMock(side_effect=capture_lpush)

    with patch("app.session._client", return_value=r):
        from app.session import add_turn
        await add_turn("sess-3", "Q", "A")

    roles = [p["role"] for p in pushed]
    contents = [p["content"] for p in pushed]
    # First push: assistant, second push: user
    assert "assistant" in roles
    assert "user" in roles
    assert "Q" in contents
    assert "A" in contents


@pytest.mark.asyncio
async def test_get_history_max_turns():
    """get_history respects MAX_TURNS*2 window."""
    items = [json.dumps({"role": "user", "content": f"msg{i}"}) for i in range(20)]
    r, _, _ = _make_redis_mock(items)
    with patch("app.session._client", return_value=r):
        from app import session
        from app.session import get_history
        # MAX_TURNS=5 → window=10
        result = await get_history("sess-4")
    assert len(result) <= session.MAX_TURNS * 2


@pytest.mark.asyncio
async def test_pool_is_lazy_and_reused(monkeypatch):
    """_client() builds the pool exactly once across calls."""
    import redis.asyncio as aredis
    import app.session as session

    # Reset module-level pool so previous tests don't bleed in.
    session._pool = None

    create_calls = {"n": 0}

    class _FakePool:
        def __init__(self):
            create_calls["n"] += 1

        async def disconnect(self, inuse_connections=True):
            pass

    class _FakeRedis:
        def __init__(self, connection_pool):
            self.pool = connection_pool

    # Patch the *attributes* on the real `redis.asyncio` module rather than
    # replacing the module itself — leaves child packages (e.g. observability)
    # importable for sibling code.
    monkeypatch.setattr(
        aredis.ConnectionPool, "from_url",
        classmethod(lambda cls, *a, **k: _FakePool()),
    )
    monkeypatch.setattr(aredis, "Redis", _FakeRedis)

    a = session._client()
    b = session._client()
    assert isinstance(a, _FakeRedis) and isinstance(b, _FakeRedis)
    assert a.pool is b.pool
    assert create_calls["n"] == 1
    # Restore module state
    session._pool = None


@pytest.mark.asyncio
async def test_aclose_pool_resets_state(monkeypatch):
    import app.session as session

    class _FakePool:
        def __init__(self):
            self.disconnected = False

        async def disconnect(self, inuse_connections=True):
            self.disconnected = True

    fake = _FakePool()
    session._pool = fake
    await session.aclose_pool()
    assert fake.disconnected is True
    assert session._pool is None
    # Calling again is a no-op.
    await session.aclose_pool()
