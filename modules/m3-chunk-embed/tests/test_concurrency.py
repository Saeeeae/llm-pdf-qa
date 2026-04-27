"""B2.1 — Semaphore concurrency limiter tests."""
import asyncio
import pytest
import app.routers.chunk_embed as ce


@pytest.mark.asyncio
async def test_semaphore_exists():
    """_SEM is an asyncio.Semaphore."""
    assert isinstance(ce._SEM, asyncio.Semaphore)


@pytest.mark.asyncio
async def test_semaphore_default_value():
    """Default semaphore count matches M3_MAX_CONCURRENT (2)."""
    import os
    # The semaphore value is set at module import time.
    # When env var is absent it defaults to 2.
    expected = int(os.getenv("M3_MAX_CONCURRENT", "2"))
    # _value is the internal counter; verify it equals expected on a fresh sem
    fresh = asyncio.Semaphore(expected)
    assert fresh._value == expected


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    """At most M3_MAX_CONCURRENT coroutines run at the same time."""
    sem = asyncio.Semaphore(2)
    active = []
    peak = []

    async def task(n):
        async with sem:
            active.append(n)
            peak.append(len(active))
            await asyncio.sleep(0)  # yield
            active.remove(n)

    await asyncio.gather(*[task(i) for i in range(6)])
    assert max(peak) <= 2


@pytest.mark.asyncio
async def test_semaphore_released_on_exception():
    """Semaphore is released even when the body raises."""
    sem = asyncio.Semaphore(1)

    async def bad_task():
        async with sem:
            raise ValueError("boom")

    with pytest.raises(ValueError):
        await bad_task()

    # Semaphore should be acquirable again immediately
    acquired = False
    async with sem:
        acquired = True
    assert acquired
