from fastapi import FastAPI

app = FastAPI(title="M4 RAG Mock", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m4-rag", "impl": "mock"}


@app.post("/rag/query")
def query(body: dict):
    web = None
    web_sources = []
    if body.get("use_web"):
        web = {
            "provider": "mock",
            "blocked": False,
            "results": [{"title": "Mock web", "url": "https://example.org", "snippet": "Mock web source."}],
        }
        web_sources = [{"doc_id": "web:1", "score": 0.0, "excerpt": "Mock web source.", "type": "web"}]
    return {
        "answer": "Mock answer for query.",
        "sources": [{"doc_id": "mock-doc-001", "score": 0.99, "excerpt": "Mock excerpt.", "type": "internal"}] + web_sources,
        "web_search": web,
    }
