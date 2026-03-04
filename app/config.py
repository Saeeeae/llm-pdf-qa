from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Document watch
    doc_watch_dir: str = "/data/documents"

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

    # Model paths (컨테이너 내 마운트 경로)
    embedding_model_dir: str = "/models/embedding"
    mineru_model_dir: str = "/models/mineru"
    llm_model_dir: str = "/models/llm"
    vlm_model_dir: str = "/models/vlm"

    # Embedding
    embed_model: str = "intfloat/multilingual-e5-large"
    embed_device: str = "cpu"
    embed_batch_size: int = 32

    # FastAPI
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Celery
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"

    # Sync schedule
    sync_cron_hour: int = 2
    sync_cron_minute: int = 0

    # HuggingFace
    hf_token: Optional[str] = None

    # JWT
    jwt_secret: str = "CHANGE_THIS_SECRET_IN_PRODUCTION_MIN_32_CHARS"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    # MinerU
    mineru_api_url: str = "http://mineru-api:9000"
    mineru_backend: str = "hybrid-auto-engine"  # pipeline (CPU), hybrid-auto-engine (pipeline+VLM), vlm-auto-engine (VLM only)
    mineru_lang: str = "korean"

    # Chunking
    chunk_strategy: str = "hybrid"  # hybrid | token
    chunk_size: int = 512
    chunk_overlap: int = 50
    chunk_min_section_tokens: int = 80

    # Image & VLM
    enable_image_embedding: bool = True
    vlm_api_url: str = "http://localhost:8001/v1"
    vlm_model_name: str = "Qwen3.5"
    image_store_dir: str = "/data/images"

    # vLLM
    vllm_api_url: str = "http://vllm-server:8001/v1"
    vllm_model_name: str = "qwen2.5-72b"

    # Web Search
    searxng_url: str = "http://searxng:8080"
    web_search_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
