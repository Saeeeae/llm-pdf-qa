import os
import random
from locust import HttpUser, task, between

TOKEN = os.getenv("LOAD_JWT", "test-token")
QUERIES = [
    "RAG란 무엇인가",
    "What is vector DB",
    "임베딩 차원",
    "Chunking strategy",
    "Hybrid search",
]


class RagUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.headers.update({"Authorization": f"Bearer {TOKEN}"})

    @task(7)
    def query(self):
        self.client.post(
            "/api/v1/chat",
            json={"query": random.choice(QUERIES), "top_k": 5},
            name="POST /chat",
        )

    @task(2)
    def docs(self):
        self.client.get(
            "/api/v1/admin/users?limit=20",
            name="GET /users",
        )

    @task(1)
    def health(self):
        self.client.get("/health", name="GET /health")
