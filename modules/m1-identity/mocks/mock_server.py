from fastapi import FastAPI

app = FastAPI(title="M1 Identity Mock", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "module": "m1-identity", "impl": "mock"}


@app.post("/auth/login")
def login(body: dict):
    return {"access_token": "mock-token-abc123", "token_type": "bearer"}
