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


@router.websocket("/admin/ws")
async def admin_ws(ws: WebSocket):
    token = ws.query_params.get("token") or ws.headers.get("authorization", "").removeprefix("Bearer ")
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
