import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from jose import JWTError, jwt


def _require_secret(name: str) -> str:
    v = os.getenv(name)
    if not v or len(v) < 32:
        raise RuntimeError(f"{name} must be set (>=32 chars)")
    return v


JWT_SECRET = _require_secret("JWT_SECRET")
ALGORITHM = "HS256"

PUBLIC_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/health",
    "/ready",
}


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "Missing token"}, status_code=401)

        token = auth[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        except JWTError:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)

        request.state.user = payload
        return await call_next(request)
