"""
E2E conftest — testcontainers (postgres/pgvector + redis) + in-process FastAPI apps.

Requirements (install with `pip install -e ".[e2e]"` from repo root or
`pip install testcontainers[postgres,redis] psycopg[binary] httpx`):
  - testcontainers>=4.0
  - psycopg[binary]>=3.1
  - httpx>=0.27
  - pytest-asyncio

When testcontainers / Docker is unavailable (sandbox / CI without DinD) the
module is imported and type-checked but the session-scoped fixture
`infra_containers` is SKIPPED automatically.
"""

from __future__ import annotations

import os
import importlib
import pytest
import pytest_asyncio

# ── Docker / testcontainers availability gate ──────────────────────────────

def _docker_available() -> bool:
    try:
        import docker  # noqa: F401
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


DOCKER_AVAILABLE = _docker_available()

# ── Monkeypatches ──────────────────────────────────────────────────────────

def _patch_m3_embedder(monkeypatch):
    """Replace SentenceTransformer with zero-vector stub (dim=1024)."""
    import numpy as np

    class _FakeModel:
        def encode(self, texts, *args, **kwargs):
            return np.zeros((len(texts), 1024), dtype="float32")

    # Patch wherever it's imported
    try:
        import app.embedder as embedder_mod  # noqa: F401
        monkeypatch.setattr(embedder_mod, "_model", _FakeModel(), raising=False)
    except ImportError:
        pass


def _patch_m4_vllm(monkeypatch):
    """Replace vLLM HTTP calls with echo stub."""
    async def _fake_generate(prompt: str, **_kwargs):
        yield f"[ECHO] {prompt[:80]}"

    try:
        import app.llm_client as llm_mod  # noqa: F401
        monkeypatch.setattr(llm_mod, "generate_stream", _fake_generate, raising=False)
    except ImportError:
        pass


# ── Container fixtures ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def infra_containers():
    """Start postgres (pgvector) + redis via testcontainers.

    Skips automatically when Docker is not available.
    Returns dict with DSNs:
      {
        "postgres_url": "postgresql+asyncpg://...",
        "postgres_sync_url": "postgresql://...",
        "redis_url": "redis://...",
      }
    """
    if not DOCKER_AVAILABLE:
        pytest.skip("Docker not available — skipping E2E infra containers")

    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    postgres = PostgresContainer("pgvector/pgvector:pg16")
    redis = RedisContainer("redis:7")

    postgres.start()
    redis.start()

    pg_sync = postgres.get_connection_url()  # postgresql://...
    # asyncpg variant
    pg_async = pg_sync.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    )
    redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"

    yield {
        "postgres_url": pg_async,
        "postgres_sync_url": pg_sync,
        "redis_url": redis_url,
    }

    postgres.stop()
    redis.stop()


# ── Per-module app fixtures ────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def m1_client(infra_containers, monkeypatch):
    """M1 Identity — in-process FastAPI via ASGI transport."""
    from httpx import AsyncClient, ASGITransport

    os.environ["TEST_MODE"] = "1"
    os.environ.setdefault("JWT_SECRET", "x" * 32)
    os.environ["POSTGRES_URL"] = infra_containers["postgres_url"]
    os.environ["REDIS_URL"] = infra_containers["redis_url"]

    # Import after env is set
    import importlib
    m1_main = importlib.import_module("app.main")
    importlib.reload(m1_main)
    app = m1_main.app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://m1") as c:
        yield c


@pytest_asyncio.fixture(scope="session")
async def m2_client(infra_containers, monkeypatch):
    """M2 Doc-to-MD — in-process FastAPI via ASGI transport."""
    from httpx import AsyncClient, ASGITransport

    os.environ["TEST_MODE"] = "1"
    os.environ["POSTGRES_URL"] = infra_containers["postgres_url"]
    os.environ["REDIS_URL"] = infra_containers["redis_url"]

    import importlib
    m2_main = importlib.import_module("app.main")
    importlib.reload(m2_main)
    app = m2_main.app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://m2") as c:
        yield c


@pytest_asyncio.fixture(scope="session")
async def m3_client(infra_containers, monkeypatch):
    """M3 Chunk/Embed — in-process, SentenceTransformer monkeypatched."""
    from httpx import AsyncClient, ASGITransport

    os.environ["TEST_MODE"] = "1"
    os.environ["POSTGRES_URL"] = infra_containers["postgres_url"]
    os.environ["REDIS_URL"] = infra_containers["redis_url"]

    _patch_m3_embedder(monkeypatch)

    import importlib
    m3_main = importlib.import_module("app.main")
    importlib.reload(m3_main)
    app = m3_main.app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://m3") as c:
        yield c


@pytest_asyncio.fixture(scope="session")
async def m4_client(infra_containers, monkeypatch):
    """M4 RAG Engine — in-process, vLLM monkeypatched with echo stub."""
    from httpx import AsyncClient, ASGITransport

    os.environ["TEST_MODE"] = "1"
    os.environ["POSTGRES_URL"] = infra_containers["postgres_url"]
    os.environ["REDIS_URL"] = infra_containers["redis_url"]
    os.environ.setdefault("VLLM_URL", "http://localhost:9999/v1")  # unreachable, patched

    _patch_m4_vllm(monkeypatch)

    import importlib
    m4_main = importlib.import_module("app.main")
    importlib.reload(m4_main)
    app = m4_main.app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://m4") as c:
        yield c


@pytest_asyncio.fixture(scope="session")
async def m5_client(infra_containers, monkeypatch):
    """M5 Gateway — in-process."""
    from httpx import AsyncClient, ASGITransport

    os.environ["TEST_MODE"] = "1"
    os.environ.setdefault("JWT_SECRET", "x" * 32)
    os.environ["REDIS_URL"] = infra_containers["redis_url"]

    import importlib
    m5_main = importlib.import_module("app.main")
    importlib.reload(m5_main)
    app = m5_main.app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://m5") as c:
        yield c
