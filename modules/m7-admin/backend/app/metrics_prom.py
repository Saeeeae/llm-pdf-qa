"""
metrics_prom.py — Prometheus instrumentation for M7 admin backend.
Exposes /metrics endpoint and provides counters/histograms.
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter, Response

router = APIRouter()

admin_requests_total = Counter(
    "admin_requests_total",
    "Total admin API requests",
    ["method", "path", "status"],
)

admin_request_duration_seconds = Histogram(
    "admin_request_duration_seconds",
    "Admin API request duration in seconds",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

admin_ws_connections = Gauge(
    "admin_ws_connections",
    "Current WebSocket connections to admin",
)


@router.get("/metrics", include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
