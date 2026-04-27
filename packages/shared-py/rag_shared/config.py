import os
from functools import lru_cache
from pydantic_settings import BaseSettings


def _require_secret(name: str) -> str:
    v = os.getenv(name)
    if not v or len(v) < 32:
        raise RuntimeError(f"{name} must be set (>=32 chars)")
    return v


class Settings(BaseSettings):
    POSTGRES_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ragdb"
    NEO4J_URL: str = "bolt://localhost:7687"
    REDIS_URL: str = "redis://localhost:6379"
    JWT_SECRET: str = ""
    MODULE_IMPL: str = "real"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
