import os
import time
from fastapi import FastAPI, Request, Response
from .routers import admin
from .routers.ws import router as ws_router
from .metrics_prom import (
    router as metrics_router,
    admin_requests_total,
    admin_request_duration_seconds,
)

app = FastAPI(
    title="M7 Admin Backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed = time.perf_counter() - start
    path = request.url.path
    admin_requests_total.labels(
        method=request.method,
        path=path,
        status=str(response.status_code),
    ).inc()
    admin_request_duration_seconds.labels(method=request.method, path=path).observe(elapsed)
    return response


@app.get("/health")
def health():
    return {"status": "ok", "module": "m7-admin", "impl": os.getenv("MODULE_IMPL", "real")}


@app.get("/ready")
def ready():
    return {"status": "ready"}


app.include_router(admin.router)
app.include_router(ws_router)
app.include_router(metrics_router)
