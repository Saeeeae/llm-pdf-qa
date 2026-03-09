from shared.config import SharedSettings


class ServingSettings(SharedSettings):
    # vLLM
    vllm_base_url: str = "http://vllm-server:8000/v1"
    vllm_model_name: str = "qwen2.5-72b"

    # Web Search
    web_search_enabled: bool = True
    google_api_key: str = ""
    google_cx: str = ""

    # Serving
    serving_api_port: int = 8002

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


serving_settings = ServingSettings()
