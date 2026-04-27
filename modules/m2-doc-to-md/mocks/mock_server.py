from fastapi import FastAPI

app = FastAPI(title="M2 Doc-to-MD Mock", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m2-doc-to-md", "impl": "mock"}


@app.post("/ingest/scan", status_code=202)
def scan(body: dict = None):
    return {"job_id": "mock-job-001", "status": "accepted", "mode": "incremental"}


@app.get("/ingest/status")
def status():
    return {"running": False, "last_run": "2026-04-21T00:00:00Z", "docs_processed": 42}
