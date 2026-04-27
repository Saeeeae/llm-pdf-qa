from prometheus_client import Counter, Histogram

documents_processed = Counter(
    "m2_documents_processed_total",
    "Documents processed",
    ["status"],
)

conversion_duration = Histogram(
    "m2_conversion_duration_seconds",
    "Conversion duration",
    buckets=(1, 5, 10, 30, 60, 300, 600),
)

m3_trigger_latency = Histogram(
    "m2_m3_trigger_latency_seconds",
    "M3 trigger latency",
)
