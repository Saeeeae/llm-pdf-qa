"""Downstream sync triggers fired after a successful m1 sync.

Kept separate from scheduler.py so the trigger logic can be unit-tested
without pulling in APScheduler.
"""
import logging
import os

import httpx

log = logging.getLogger(__name__)


async def trigger_m2() -> None:
    """POST to m2's internal sync endpoint. Non-blocking on failure.

    m1 success is the prerequisite — caller must only invoke this when its
    own sync row is committed as success. Network/HTTP failures here are
    logged but never raised, since the m1 sync itself has already landed
    and downstream retry is m2's responsibility.
    """
    url = os.getenv("M2_INTERNAL_SYNC_URL")
    if not url:
        log.info("M2_INTERNAL_SYNC_URL unset — skipping m2 trigger")
        return
    token = os.getenv("INTERNAL_SYNC_TOKEN", "")
    if not token:
        # Loud signal: URL set but token missing → m2 will 401 every call.
        # Easy to miss otherwise since the warning catch below is generic.
        log.error(
            "M2_INTERNAL_SYNC_URL set but INTERNAL_SYNC_TOKEN is empty — "
            "m2 trigger will be rejected (401). Set INTERNAL_SYNC_TOKEN."
        )
        return
    timeout = float(os.getenv("M2_TRIGGER_TIMEOUT_SECONDS", "5"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={"X-Internal-Token": token},
                json={"source": "m1-scheduler"},
            )
            resp.raise_for_status()
            log.info("m2 sync triggered (%s)", resp.status_code)
    except Exception as e:
        log.warning("m2 trigger failed (m1 sync still marked success): %s", e)
