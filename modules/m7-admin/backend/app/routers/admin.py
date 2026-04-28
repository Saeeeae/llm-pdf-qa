"""
admin.py — M7 Admin API router.
All endpoints require appropriate permissions (verified via JWT from M1/M5).
"""
import asyncio
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional

import httpx
import psutil
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from jose import jwt

from ..auth import require_permission, _SECRET as _JWT_SECRET
from ..cache import cache_get, cache_set
from ..db import get_db, check_db_connectivity

router = APIRouter(prefix="/admin")
_JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

_M_URLS = {
    "m1": os.getenv("M1_URL", "http://m1-identity:8000"),
    "m2": os.getenv("M2_URL", "http://m2-ingest:8000"),
    "m3": os.getenv("M3_URL", "http://m3-chunk-embed:8000"),
    "m4": os.getenv("M4_URL", "http://m4-rag:8000"),
    "m5": os.getenv("M5_URL", "http://m5-gateway:8080"),
    "m8": os.getenv("M8_URL", "http://m8-web-search:8000"),
}


# ---------- Audit Log ----------

@router.get("/audit-log")
async def audit_log(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    db=Depends(get_db),
    _: dict = Depends(require_permission("audit.read")),
):
    from sqlalchemy import text

    # m1 schema uses `ts` (not `created_at`) and a single `resource` column.
    # We alias them to keep the JSON contract stable for downstream consumers.
    offset = (page - 1) * size
    base = (
        "SELECT id, user_id, action, "
        "resource AS resource_type, NULL::text AS resource_id, "
        "ts AS created_at, metadata "
        "FROM audit_log WHERE 1=1"
    )
    count_base = "SELECT COUNT(*) FROM audit_log WHERE 1=1"
    conds, params = [], {}
    if user_id:
        conds.append(" AND user_id = :user_id")
        params["user_id"] = user_id
    if action:
        conds.append(" AND action = :action")
        params["action"] = action
    if from_:
        conds.append(" AND ts >= :from_ts")
        params["from_ts"] = from_
    if to:
        conds.append(" AND ts <= :to_ts")
        params["to_ts"] = to

    suffix = "".join(conds)
    rows = await db.execute(
        text(base + suffix + " ORDER BY ts DESC LIMIT :limit OFFSET :offset"),
        {**params, "limit": size, "offset": offset},
    )
    count_row = await db.execute(text(count_base + suffix), params)
    total = count_row.scalar_one()
    entries = [dict(r._mapping) for r in rows]
    return {"entries": entries, "total": total, "page": page, "size": size}


# ---------- Users ----------

@router.get("/users")
async def list_users(
    role: Optional[str] = None,
    department: Optional[str] = None,
    db=Depends(get_db),
    _: dict = Depends(require_permission("admin.read")),
):
    from sqlalchemy import text

    # m1 schema uses normalized FKs (role_id, department_id). Join the lookup
    # tables and project the human-readable names.
    base = (
        "SELECT u.id AS user_id, u.email, u.name, "
        "       r.name AS role, d.name AS department, "
        "       u.is_active, u.last_login_at "
        "FROM users u "
        "LEFT JOIN roles r ON u.role_id = r.id "
        "LEFT JOIN department d ON u.department_id = d.id "
        "WHERE 1=1"
    )
    conds, params = [], {}
    if role:
        conds.append(" AND r.name = :role")
        params["role"] = role
    if department:
        conds.append(" AND d.name = :department")
        params["department"] = department

    rows = await db.execute(text(base + "".join(conds) + " ORDER BY email"), params)
    return {"users": [dict(r._mapping) for r in rows]}


# ---------- Metrics — Embedding ----------

@router.get("/metrics/embedding")
async def metrics_embedding(
    _: dict = Depends(require_permission("admin.read")),
):
    cached = await cache_get("metrics:embedding")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_M_URLS['m3']}/chunk-embed/stats")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        data = {"error": str(e)}

    await cache_set("metrics:embedding", data, ttl=30)
    return data


# ---------- Metrics — Chunking ----------

@router.get("/metrics/chunking")
async def metrics_chunking(
    _: dict = Depends(require_permission("admin.read")),
):
    cached = await cache_get("metrics:chunking")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_M_URLS['m3']}/chunker/stats")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        data = {"error": str(e)}

    await cache_set("metrics:chunking", data, ttl=30)
    return data


# ---------- Metrics — GPU ----------

@router.get("/metrics/gpu")
async def metrics_gpu(
    _: dict = Depends(require_permission("admin.read")),
):
    cached = await cache_get("metrics:gpu")
    if cached:
        return cached

    data: dict = {}
    try:
        # nvidia-smi query — returns CSV: utilization.gpu,memory.used,memory.total
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            data = {
                "utilization_pct": float(parts[0]),
                "memory_used_mb": float(parts[1]),
                "memory_total_mb": float(parts[2]),
            }
        else:
            data = {"error": "nvidia-smi not available"}
    except FileNotFoundError:
        data = {"error": "nvidia-smi not found"}
    except Exception as e:
        data = {"error": str(e)}

    await cache_set("metrics:gpu", data, ttl=30)
    return data


# ---------- Metrics — Server ----------

@router.get("/metrics/server")
async def metrics_server(
    _: dict = Depends(require_permission("admin.read")),
):
    cpu = psutil.cpu_percent(interval=0.5)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_pct": cpu,
        "ram_used_mb": round(vm.used / 1024 / 1024, 1),
        "ram_total_mb": round(vm.total / 1024 / 1024, 1),
        "ram_pct": vm.percent,
        "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
        "disk_pct": disk.percent,
    }


# ---------- Health Aggregate ----------

@router.get("/health/aggregate")
async def health_aggregate(
    _: dict = Depends(require_permission("admin.read")),
):
    async def probe(name: str, url: str):
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{url}/ready")
            return {"name": name, "status": "ok" if r.status_code < 400 else "degraded",
                    "checked_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            return {"name": name, "status": "down", "error": str(e),
                    "checked_at": datetime.now(timezone.utc).isoformat()}

    service_probes = [probe(k, v) for k, v in _M_URLS.items()]
    db_ok = await check_db_connectivity()
    redis_ok_val = False
    try:
        from ..cache import check_redis_connectivity
        redis_ok_val = await check_redis_connectivity()
    except Exception:
        pass

    results = await asyncio.gather(*service_probes)
    infra = [
        {"name": "postgres", "status": "ok" if db_ok else "down",
         "checked_at": datetime.now(timezone.utc).isoformat()},
        {"name": "redis", "status": "ok" if redis_ok_val else "down",
         "checked_at": datetime.now(timezone.utc).isoformat()},
    ]
    return {"services": list(results) + infra}


# ---------- Logs — Query ----------

@router.get("/logs/query")
async def logs_query(
    limit: int = Query(100, ge=1, le=1000),
    db=Depends(get_db),
    _: dict = Depends(require_permission("audit.read")),
):
    from sqlalchemy import text

    rows = await db.execute(
        text(
            "SELECT al.id, al.user_id, u.email, al.ts AS created_at, "
            "al.metadata->>'latency_ms' AS latency_ms, "
            "al.metadata->>'status' AS status, "
            "al.metadata->>'query' AS query "
            "FROM audit_log al "
            "LEFT JOIN users u ON u.id = al.user_id "
            "WHERE al.action = 'chat.query' "
            "ORDER BY al.ts DESC LIMIT :limit"
        ),
        {"limit": limit},
    )
    return {"entries": [dict(r._mapping) for r in rows]}


# ---------- Pipeline Runs ----------

@router.get("/pipeline/runs")
async def pipeline_runs(
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    _: dict = Depends(require_permission("admin.read")),
):
    from sqlalchemy import text

    rows = await db.execute(
        text(
            "SELECT id, user_id, ts AS created_at, "
            "metadata->>'doc_count' AS doc_count, "
            "metadata->>'duration_s' AS duration_s, "
            "metadata->>'failures' AS failures, "
            "metadata->>'status' AS status "
            "FROM audit_log "
            "WHERE action = 'pipeline.run' "
            "ORDER BY ts DESC LIMIT :limit"
        ),
        {"limit": limit},
    )
    return {"runs": [dict(r._mapping) for r in rows]}


# ---------- Web Search ----------

@router.get("/web-search/providers")
async def web_search_providers(
    _: dict = Depends(require_permission("admin.read")),
):
    cached = await cache_get("web-search:providers")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_M_URLS['m8']}/web-search/providers")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        data = {"providers": [], "error": str(e)}

    await cache_set("web-search:providers", data, ttl=30)
    return data


@router.get("/web-search/audit-summary")
async def web_search_audit_summary(
    _: dict = Depends(require_permission("audit.read")),
):
    cached = await cache_get("web-search:audit-summary")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_M_URLS['m8']}/web-search/audit/summary")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        data = {
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
            "error": str(e),
        }

    await cache_set("web-search:audit-summary", data, ttl=30)
    return data


@router.get("/web-search/policy")
async def web_search_policy(
    _: dict = Depends(require_permission("admin.read")),
):
    return {
        "default_provider": os.getenv("M8_DEFAULT_PROVIDER", "curated"),
        "allowed_domains": [d.strip() for d in os.getenv("M8_ALLOWED_DOMAINS", "").split(",") if d.strip()],
        "denied_domains": [d.strip() for d in os.getenv("M8_DENIED_DOMAINS", "").split(",") if d.strip()],
        "confidential_terms_configured": bool(os.getenv("M8_CONFIDENTIAL_TERMS", "")),
        "egress_boundary": "m8-web-search",
    }


# ---------- Impersonate ----------

@router.post("/users/{user_id}/impersonate")
async def impersonate(
    user_id: str,
    db=Depends(get_db),
    actor: dict = Depends(require_permission("admin.write")),
):
    from sqlalchemy import text

    # Verify target user exists and fetch their role permissions
    row = await db.execute(
        text(
            "SELECT u.id AS user_id, u.email, r.name AS role, r.permissions "
            "FROM users u LEFT JOIN roles r ON r.id = u.role_id "
            "WHERE u.id = :uid"
        ),
        {"uid": user_id},
    )
    target = row.mappings().first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Issue short-lived (10 min) impersonation token
    import time
    import json as _json2
    raw_perms = target["permissions"]
    perms: list = raw_perms if isinstance(raw_perms, list) else (_json2.loads(raw_perms) if raw_perms else [])
    payload = {
        "sub": user_id,
        "email": target["email"],
        "role": target["role"],
        "permissions": perms,
        "perm": perms,
        "impersonated_by": actor.get("sub"),
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }
    token = jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)

    # Audit log the impersonation
    import json as _json
    # m1.audit_log has a single `resource` column; encode the target user id into it.
    await db.execute(
        text(
            "INSERT INTO audit_log (user_id, action, resource, metadata) "
            "VALUES (:uid, 'admin.impersonate', :target_resource, :meta::jsonb)"
        ),
        {
            "uid": actor.get("sub"),
            "target_resource": f"user:{user_id}",
            "meta": _json.dumps({
                "actor": str(actor.get("sub")),
                "target_user_id": user_id,
            }),
        },
    )
    await db.commit()

    return {"access_token": token, "token_type": "bearer", "expires_in": 600}


# ---------- CSV Export ----------

@router.get("/export/audit-log.csv")
async def export_audit_log_csv(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    db=Depends(get_db),
    _: dict = Depends(require_permission("audit.read")),
):
    from sqlalchemy import text

    base = (
        "SELECT id, user_id, action, "
        "resource AS resource_type, NULL::text AS resource_id, "
        "ts AS created_at "
        "FROM audit_log WHERE 1=1"
    )
    conds, params = [], {}
    if user_id:
        conds.append(" AND user_id = :user_id")
        params["user_id"] = user_id
    if action:
        conds.append(" AND action = :action")
        params["action"] = action
    if from_:
        conds.append(" AND ts >= :from_ts")
        params["from_ts"] = from_
    if to:
        conds.append(" AND ts <= :to_ts")
        params["to_ts"] = to

    rows = await db.execute(text(base + "".join(conds) + " ORDER BY ts DESC"), params)
    records = rows.fetchall()

    def generate():
        yield "id,user_id,action,resource_type,resource_id,created_at\n"
        for r in records:
            yield ",".join(str(v) if v is not None else "" for v in r) + "\n"

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )
