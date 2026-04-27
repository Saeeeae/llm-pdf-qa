from fastapi import FastAPI

app = FastAPI(title="M8 Web Search Mock", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m8-web-search", "impl": "mock"}


@app.get("/ready")
def ready():
    return {"status": "ok", "default_provider": "mock"}


@app.post("/web-search/search")
def search(body: dict):
    query = body.get("query", "")
    return {
        "provider": "mock",
        "safe_query": query,
        "query_hash": "mock-hash",
        "blocked": False,
        "results": [
            {
                "title": "Mock web result",
                "url": "https://example.org/mock-result",
                "snippet": "Mock M8 result.",
                "source": "mock",
            }
        ],
        "citations": [
            {
                "title": "Mock web result",
                "url": "https://example.org/mock-result",
                "snippet": "Mock M8 result.",
                "source": "mock",
            }
        ],
        "audit_id": "mock-audit",
    }


@app.get("/web-search/providers")
def providers():
    return {"providers": [{"name": "mock", "configured": True, "external": False}]}


@app.get("/web-search/audit/summary")
def audit_summary():
    return {"total": 0, "allowed": 0, "blocked": 0, "providers": {}, "recent": []}
