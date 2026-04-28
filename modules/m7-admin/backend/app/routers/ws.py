"""
ws.py — WebSocket endpoint for real-time admin events.
Subscribes to Redis pub/sub channels: audit_events, pipeline_events.
M1 publishes to audit_events on each write action.
M2/M3 publish to pipeline_events on ingestion/embedding progress.
"""
import asyncio
import json
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
import redis.asyncio as aioredis

from ..auth import decode_token

router = APIRouter()

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_CHANNELS = ["audit_events", "pipeline_events"]


def _extract_token(ws: WebSocket) -> str:
    """
    Extract bearer token without leaking it to access logs.
    Order: Authorization header → Sec-WebSocket-Protocol subprotocol →
    ?token= query param (only if WS_ALLOW_QUERY_TOKEN=1, default off).
    """
    auth = ws.headers.get("authorization", "")
    if auth:
        return auth.removeprefix("Bearer ").strip()
    # Sec-WebSocket-Protocol can carry "bearer, <token>" from browsers.
    proto = ws.headers.get("sec-websocket-protocol", "")
    if proto:
        parts = [p.strip() for p in proto.split(",") if p.strip()]
        if len(parts) >= 2 and parts[0].lower() == "bearer":
            return parts[1]
    if os.getenv("WS_ALLOW_QUERY_TOKEN") == "1":
        return ws.query_params.get("token", "")
    return ""


@router.websocket("/admin/ws")
async def admin_ws(ws: WebSocket):
    token = _extract_token(ws)
    try:
        payload = decode_token(token)
        perms = payload.get("permissions") or payload.get("perm", [])
        if "admin.read" not in perms:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws.accept()
    redis = aioredis.from_url(_REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(*_CHANNELS)

    try:
        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue
            try:
                await ws.send_text(json.dumps({
                    "channel": msg["channel"],
                    "data": json.loads(msg["data"]) if isinstance(msg["data"], str) else msg["data"],
                }))
            except Exception:
                break
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await pubsub.unsubscribe(*_CHANNELS)
        await pubsub.close()
        await redis.aclose()
