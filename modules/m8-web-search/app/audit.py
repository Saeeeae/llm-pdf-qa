from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def audit_path() -> Path:
    return Path(os.getenv("M8_AUDIT_LOG", "/tmp/m8_web_search_audit.jsonl"))


def write_audit(event: dict[str, Any]) -> str:
    audit_id = str(uuid.uuid4())
    payload = {
        "audit_id": audit_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return audit_id


def read_summary() -> dict[str, Any]:
    path = audit_path()
    if not path.exists():
        return {
            "total": 0,
            "allowed": 0,
            "blocked": 0,
            "failed": 0,
            "cache_hits": 0,
            "external": 0,
            "failure_rate": 0.0,
            "estimated_cost_usd": 0.0,
            "providers": {},
            "recent": [],
        }

    total = allowed = blocked = 0
    failed = cache_hits = external = 0
    providers: dict[str, int] = {}
    recent: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            if event.get("blocked"):
                blocked += 1
            else:
                allowed += 1
            if event.get("failed"):
                failed += 1
            if event.get("action") == "web_search.cache_hit":
                cache_hits += 1
            if event.get("external"):
                external += 1
            provider = event.get("provider", "unknown")
            providers[provider] = providers.get(provider, 0) + 1
            recent.append(event)
            recent = recent[-20:]

    return {
        "total": total,
        "allowed": allowed,
        "blocked": blocked,
        "failed": failed,
        "cache_hits": cache_hits,
        "external": external,
        "failure_rate": round(failed / total, 4) if total else 0.0,
        "estimated_cost_usd": 0.0,
        "providers": providers,
        "recent": recent,
    }
