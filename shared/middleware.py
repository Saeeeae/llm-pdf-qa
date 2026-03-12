"""FastAPI Request Logging Middleware.

Adds per-request trace_id, logs request/response timing to event_log,
and provides IP extraction for audit purposes.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from shared.event_logger import get_event_logger, set_request_context

elog = get_event_logger("system")


def get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For or direct connection."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs every HTTP request/response to event_log.

    Skips health checks and static files to avoid noise.
    """

    SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip noisy endpoints
        if path in self.SKIP_PATHS or path.startswith("/admin/"):
            return await call_next(request)

        # Set request context (trace_id, ip)
        ip = get_client_ip(request)
        trace_id = set_request_context(ip_address=ip)

        # Attach trace_id to request state for downstream use
        request.state.trace_id = trace_id

        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            elog.error(
                f"{request.method} {path} → 500",
                error=e,
                duration_ms=duration_ms,
                details={"method": request.method, "path": path},
            )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)

        # Log slow requests (>2s) at warning level, others at debug
        if duration_ms > 2000:
            elog.warning(
                f"Slow request: {request.method} {path} → {response.status_code}",
                duration_ms=duration_ms,
                details={"method": request.method, "path": path, "status": response.status_code},
            )
        elif response.status_code >= 400:
            elog.warning(
                f"{request.method} {path} → {response.status_code}",
                duration_ms=duration_ms,
                details={"method": request.method, "path": path, "status": response.status_code},
            )

        # Add trace_id header for client debugging
        response.headers["X-Trace-ID"] = trace_id
        return response
