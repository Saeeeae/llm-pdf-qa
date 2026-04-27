from fastapi import FastAPI

app = FastAPI(title="M5 Gateway Mock", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m5-gateway", "impl": "mock"}


@app.get("/api/v1/me")
def me():
    return {"user_id": "mock-usr-001", "email": "mock@example.com", "role": "user"}


@app.post("/api/v1/chat")
def chat(body: dict):
    return {"reply": "Mock reply.", "sources": []}
