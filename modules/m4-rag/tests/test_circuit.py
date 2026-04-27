"""B2.5 — Circuit breaker tests."""
import time
import pytest
from app.llm_client import CB


def test_cb_starts_closed():
    cb = CB(threshold=3, recovery=30)
    assert cb.can_call() is True


def test_cb_opens_after_threshold():
    cb = CB(threshold=3, recovery=30)
    for _ in range(3):
        cb.record(False)
    assert cb.can_call() is False


def test_cb_not_open_below_threshold():
    cb = CB(threshold=3, recovery=30)
    cb.record(False)
    cb.record(False)
    assert cb.can_call() is True


def test_cb_resets_on_success():
    cb = CB(threshold=3, recovery=30)
    for _ in range(3):
        cb.record(False)
    assert cb.can_call() is False
    cb.record(True)
    assert cb.fails == 0
    assert cb.can_call() is True


def test_cb_recovers_after_timeout(monkeypatch):
    cb = CB(threshold=2, recovery=1)
    for _ in range(2):
        cb.record(False)
    assert cb.can_call() is False

    # Fast-forward time past recovery window
    monkeypatch.setattr(time, "time", lambda: cb.opened_at + 2)
    assert cb.can_call() is True


def test_cb_stays_open_within_recovery(monkeypatch):
    cb = CB(threshold=2, recovery=30)
    for _ in range(2):
        cb.record(False)
    monkeypatch.setattr(time, "time", lambda: cb.opened_at + 10)
    assert cb.can_call() is False


@pytest.mark.asyncio
async def test_generate_stream_raises_when_open():
    """generate_stream raises RuntimeError when circuit is open."""
    import app.llm_client as lc
    original_cb = lc._cb
    try:
        cb = CB(threshold=1, recovery=9999)
        cb.record(False)  # open immediately
        lc._cb = cb
        with pytest.raises(RuntimeError, match="vllm circuit open"):
            async for _ in lc.generate_stream([]):
                pass
    finally:
        lc._cb = original_cb
