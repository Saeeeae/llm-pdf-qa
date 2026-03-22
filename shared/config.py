# shared/config.py
from pydantic_settings import BaseSettings
from typing import Optional


class SharedSettings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "rag_system"
    postgres_user: str = "admin"
    postgres_password: str = "changeme"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Neo4j
    neo4j_url: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Celery
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # Embedding
    embedding_model_name: str = "BAAI/bge-m3"
    embedding_model_dir: str = "/models/embedding"
    embedding_device: str = "cuda"
    embedding_batch_size: int = 32

    # Reranker
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    reranker_model_dir: str = "/models/reranker"
    reranker_device: str = "cuda"

    # vLLM / generation
    vllm_base_url: str = "http://vllm-server:8000/v1"
    vllm_model_name: str = "local-llm"

    # JWT
    jwt_secret: str = "CHANGE_THIS_SECRET_IN_PRODUCTION_MIN_32_CHARS"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    # HuggingFace
    hf_token: Optional[str] = None

    # Development / smoke validation
    smoke_test_mode: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


shared_settings = SharedSettings()
