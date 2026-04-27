"""
Spike test scenario: ramp 0 → 200 concurrent users over 30 seconds,
hold for 2 minutes, then ramp back down.

Usage:
    locust -f loadtest/scenarios/spike.py --host=http://localhost:8000 \
           --headless --csv=loadtest/results/spike
"""
import os
import random
from locust import HttpUser, task, between
from locust import LoadTestShape

TOKEN = os.getenv("LOAD_JWT", "test-token")
QUERIES = [
    "RAG란 무엇인가",
    "What is vector DB",
    "임베딩 차원",
    "Chunking strategy",
    "Hybrid search",
]


class SpikeShape(LoadTestShape):
    """
    Ramp from 0 to 200 users over 30 s, hold for 120 s, then drop to 0.

    stages:
      0–30 s:   linear ramp 0 → 200 (spawn_rate = 200/30 ≈ 7)
      30–150 s: hold at 200
      150–180 s: ramp down 200 → 0 (spawn_rate = 200/30 ≈ 7)
    """

    stages = [
        {"duration": 30, "users": 200, "spawn_rate": 7},
        {"duration": 150, "users": 200, "spawn_rate": 7},
        {"duration": 180, "users": 0, "spawn_rate": 7},
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None  # stop test


class SpikeUser(HttpUser):
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
