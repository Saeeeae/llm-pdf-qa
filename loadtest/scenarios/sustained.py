"""
Sustained load scenario: 100 concurrent users, 30 minutes.

This file is a convenience wrapper; the same scenario can be run directly
from the main locustfile with CLI flags:

    locust -f loadtest/locustfile.py --host=http://localhost:8000 \
           -u 100 -r 10 -t 30m --headless --csv=loadtest/results/sustained

Usage (via this file):
    locust -f loadtest/scenarios/sustained.py --host=http://localhost:8000 \
           --headless --csv=loadtest/results/sustained
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


class SustainedShape(LoadTestShape):
    """
    Ramp to 100 users at rate 10/s, hold for 30 minutes.

    CLI equivalent: -u 100 -r 10 -t 30m
    """

    def tick(self):
        run_time = self.get_run_time()
        if run_time < 1800:  # 30 minutes
            return 100, 10
        return None  # stop test


class SustainedUser(HttpUser):
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
