from fastapi import FastAPI

app = FastAPI(title="M7 Admin Mock", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m7-admin", "impl": "mock"}


@app.get("/admin/health")
def system_health():
    return {"services": [{"name": "all", "status": "ok"}]}


@app.get("/admin/audit-log")
def audit_log():
    return {"entries": [], "total": 0}


@app.get("/admin/metrics")
def metrics():
    return {"queries_total": 100, "queries_last_24h": 10, "avg_latency_ms": 250.0}
