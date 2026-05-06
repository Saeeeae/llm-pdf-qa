"""Internal endpoints for m2's in-house DB sync.

Triggered by m1-identity after a successful identity sync (via shared
INTERNAL_SYNC_TOKEN), or manually for testing. The endpoint returns 202
immediately and runs the sync in the background, guarded by a Redis lock
to prevent overlapping runs.
"""
import logging
import os
import secrets

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from ..sync.state import load_state
from ..sync.syncer import run_sync

router = APIRouter(prefix="/internal/sync", tags=["sync"])
log = logging.getLogger("m2.sync")

_LOCK_KEY = "m2:sync:lock"
_DEFAULT_LOCK_TTL = 1800  # 30 min — see SYNC_LOCK_TTL_SECONDS env override


def _lock_ttl() -> int:
    return int(os.getenv("SYNC_LOCK_TTL_SECONDS", str(_DEFAULT_LOCK_TTL)))


def _redis_url() -> str:
    # Default targets the in-network redis service, not localhost.
    return os.getenv("REDIS_URL", "redis://redis:6379/0")


def _check_token(provided: str | None) -> None:
    expected = os.getenv("INTERNAL_SYNC_TOKEN", "")
    if not expected:
        # If the operator forgot to set the shared secret, every trigger
        # will 401 — log loudly so it's easy to spot in container logs.
        log.error(
            "INTERNAL_SYNC_TOKEN is not set — all /internal/sync calls "
            "will return 401. Set the env var to enable m1→m2 trigger."
        )
        raise HTTPException(status_code=401, detail="invalid token")
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid token")


async def _run_locked() -> None:
    r = aioredis.from_url(_redis_url())
    try:
        acquired = await r.set(_LOCK_KEY, "1", nx=True, ex=_lock_ttl())
        if not acquired:
            log.info("m2 sync skipped — lock held")
            return
        await run_sync()
    finally:
        try:
            await r.delete(_LOCK_KEY)
        except Exception:
            pass
        await r.aclose()


@router.post("/mysql", status_code=202)
async def trigger_mysql_sync(
    bg: BackgroundTasks,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    """Kick off a background MySQL sync. Token-gated."""
    _check_token(x_internal_token)
    bg.add_task(_run_locked)
    return {"status": "accepted"}


@router.get("/mysql/status")
async def mysql_sync_status(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    """Return last_run + recent history. Token-gated."""
    _check_token(x_internal_token)
    state = load_state()
    return {
        "last_run": state.get("last_run"),
        "history": state.get("history", [])[:10],
        "files_cached": len(state.get("files", {})),
        "folder_perms_cached": len(state.get("folder_perms", {})),
    }
