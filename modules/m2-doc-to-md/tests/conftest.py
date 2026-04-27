import fakeredis
import pytest


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Patch get_redis() in lock and dlq to use fakeredis."""
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)

    monkeypatch.setattr("app.pipeline.lock.get_redis", lambda: fake)
    monkeypatch.setattr("app.pipeline.dlq.get_redis", lambda: fake)
    yield fake
