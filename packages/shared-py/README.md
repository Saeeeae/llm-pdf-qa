# rag-shared

Installable Python package shared across all backend modules. Provides `get_settings` (pydantic-settings), `get_db` (SQLAlchemy session factory), `setup_logging` (JSON stdout logger), and `call_service` (httpx async client with circuit-breaker hook). Install locally with `pip install -e packages/shared-py`.
