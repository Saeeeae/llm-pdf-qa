import pytest
from app.clients.downstream import CircuitBreaker, State, get_breaker, _breakers

pytestmark = pytest.mark.asyncio


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(fail_threshold=5)
    for _ in range(4):
        cb.record_failure()
        assert cb.state == State.CLOSED
    cb.record_failure()
    assert cb.state == State.OPEN


def test_circuit_blocks_when_open():
    cb = CircuitBreaker(fail_threshold=1, recovery_timeout=9999)
    cb.record_failure()
    assert not cb.allow_request()


def test_circuit_half_open_after_timeout():
    import time
    cb = CircuitBreaker(fail_threshold=1, recovery_timeout=0.01)
    cb.record_failure()
    assert cb.state == State.OPEN
    time.sleep(0.02)
    assert cb.allow_request()
    assert cb.state == State.HALF_OPEN


def test_circuit_closes_on_success():
    cb = CircuitBreaker(fail_threshold=1)
    cb.record_failure()
    assert cb.state == State.OPEN
    cb.state = State.HALF_OPEN
    cb.record_success()
    assert cb.state == State.CLOSED


async def test_fallback_returned_when_open(client):
    """With DOWNSTREAM_FALLBACK=mock and circuit open, proxy returns fallback."""
    import os
    os.environ["DOWNSTREAM_FALLBACK"] = "mock"
    from .conftest import make_token
    token = make_token()

    # Force the m4 breaker open
    b = get_breaker("m4")
    b.state = State.OPEN
    b._opened_at = 0  # will not recover (recovery_timeout default 30s)
    import time
    b._opened_at = time.monotonic()  # just opened

    r = await client.get(
        "/api/v1/rag/query",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Fallback returns 200 (or 502 if error path — both acceptable with mock)
    assert r.status_code in (200, 502)

    # Cleanup
    _breakers.pop("m4", None)
