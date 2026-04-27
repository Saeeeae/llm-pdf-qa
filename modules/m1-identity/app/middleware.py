import json
import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("m1-identity")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        user_id = getattr(request.state, "user_id", None)
        logger.info(json.dumps({
            "request_id": request_id,
            "user_id": user_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }))
        return response
