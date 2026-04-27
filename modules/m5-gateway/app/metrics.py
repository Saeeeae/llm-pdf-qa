from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["path", "method", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["path", "method"],
)

downstream_errors_total = Counter(
    "downstream_errors_total",
    "Downstream errors",
    ["target"],
)


def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
