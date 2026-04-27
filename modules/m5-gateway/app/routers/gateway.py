import os
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from ..audit import log_audit
from ..clients.downstream import proxy_request

router = APIRouter(prefix="/api/v1")

M1_URL = os.getenv("M1_URL", "http://m1-identity:8000")
M2_URL = os.getenv("M2_URL", "http://m2-ingest:8000")
M3_URL = os.getenv("M3_URL", "http://m3-chunk-embed:8000")
M4_URL = os.getenv("M4_URL", "http://m4-rag:8000")
M7_URL = os.getenv("M7_URL", "http://m7-admin:8000")
M8_URL = os.getenv("M8_URL", "http://m8-web-search:8000")


def _forbidden_if_missing(request: Request, permission: str) -> Optional[JSONResponse]:
    user = getattr(request.state, "user", None)
    perms = (user or {}).get("permissions") or (user or {}).get("perm", [])
    if permission not in perms:
        return JSONResponse({"detail": f"Missing {permission} permission"}, status_code=403)
    return None


async def _proxy(request: Request, base_url: str, target: str) -> Response:
    path = request.url.path.removeprefix("/api/v1")
    target_url = base_url + path
    request.state.downstream_target = target
    try:
        resp = await proxy_request(request, target_url, target)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
            media_type=resp.headers.get("content-type"),
        )
    except Exception:
        from ..metrics import downstream_errors_total
        downstream_errors_total.labels(target=target).inc()
        return JSONResponse({"detail": f"Upstream error: {target}"}, status_code=502)


@router.api_route(
    "/auth/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_m1_auth(path: str, request: Request):
    return await _proxy(request, M1_URL, "m1")


@router.api_route(
    "/users/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_m1_users(path: str, request: Request):
    return await _proxy(request, M1_URL, "m1")


@router.api_route(
    "/ingest/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_m2(path: str, request: Request):
    return await _proxy(request, M2_URL, "m2")


@router.api_route(
    "/pipeline/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_m3(path: str, request: Request):
    return await _proxy(request, M3_URL, "m3")


@router.api_route(
    "/rag/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_m4(path: str, request: Request):
    return await _proxy(request, M4_URL, "m4")


@router.api_route(
    "/admin/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_m7(path: str, request: Request):
    return await _proxy(request, M7_URL, "m7")


@router.api_route(
    "/web-search/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_m8(path: str, request: Request):
    forbidden = _forbidden_if_missing(request, "web.search")
    if forbidden:
        log_audit(
            "web_search.denied",
            getattr(request.state, "user", None),
            request_id=getattr(request.state, "request_id", None),
            reason="missing_permission",
            method=request.method,
            path=request.url.path,
        )
        return forbidden
    log_audit(
        "web_search.proxy",
        getattr(request.state, "user", None),
        request_id=getattr(request.state, "request_id", None),
        method=request.method,
        path=request.url.path,
    )
    return await _proxy(request, M8_URL, "m8")
