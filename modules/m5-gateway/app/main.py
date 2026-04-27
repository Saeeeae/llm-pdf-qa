import os
import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from rag_shared.logging import setup_logging

from .metrics import metrics_endpoint
from .middleware.auth import JWTAuthMiddleware
from .middleware.ratelimit import RateLimitMiddleware
from .middleware.security import SecurityHeadersMiddleware
from .middleware.tracing import TracingMiddleware
from .routers import gateway, chat

_basic = HTTPBasic(auto_error=False)


def _metrics_auth(creds: HTTPBasicCredentials = Depends(_basic)):
    user = os.getenv("METRICS_USER", "metrics")
    pw = os.getenv("METRICS_PASSWORD", "")
    if not pw:
        return  # no password configured — allow (dev mode)
    ok = creds and secrets.compare_digest(creds.username, user) and secrets.compare_digest(creds.password, pw)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            headers={"WWW-Authenticate": "Basic"})

setup_logging("m5-gateway")

app = FastAPI(title="M5 API Gateway", version="1.0.0")

# CORS
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TracingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(JWTAuthMiddleware)

app.include_router(gateway.router)
app.include_router(chat.router)


@app.get("/health")
def health():
    return {"status": "ok", "module": "m5-gateway"}


@app.get("/ready")
async def ready():
    import httpx
    M1_URL = os.getenv("M1_URL", "http://m1-identity:8000")
    M2_URL = os.getenv("M2_URL", "http://m2-ingest:8000")
    M3_URL = os.getenv("M3_URL", "http://m3-chunk-embed:8000")
    M4_URL = os.getenv("M4_URL", "http://m4-rag:8000")
    M7_URL = os.getenv("M7_URL", "http://m7-admin:8000")
    M8_URL = os.getenv("M8_URL", "http://m8-web-search:8000")

    critical = {"m1": M1_URL, "m4": M4_URL}
    optional = {"m2": M2_URL, "m3": M3_URL, "m7": M7_URL, "m8": M8_URL}

    async def check(url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{url}/health")
                return r.status_code == 200
        except Exception:
            return False

    results = {}
    for name, url in {**critical, **optional}.items():
        results[name] = await check(url)

    failed_critical = [k for k in critical if not results[k]]
    failed_optional = [k for k in optional if not results[k]]

    if failed_critical:
        return {"status": "unavailable", "failed": failed_critical + failed_optional}, 503
    if failed_optional:
        return {"status": "degraded", "failed": failed_optional, "healthy": True}
    return {"status": "ok"}


@app.get("/metrics")
def metrics(_: None = Depends(_metrics_auth)):
    return metrics_endpoint()
