from fastapi import FastAPI

app = FastAPI(title="M3 Chunk/Embed Mock", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m3-chunk-embed", "impl": "mock"}


@app.post("/chunk-embed")
def chunk_embed(body: dict):
    return {"doc_id": body.get("doc_id", "mock-doc"), "chunks": 12, "status": "done"}
