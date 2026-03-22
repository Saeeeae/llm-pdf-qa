from shared.config import SharedSettings


class ServingSettings(SharedSettings):
    # Web Search
    web_search_enabled: bool = True
    google_api_key: str = ""
    google_cx: str = ""

    # Serving
    serving_api_port: int = 8002
    prefer_env_llm_config: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


serving_settings = ServingSettings()
