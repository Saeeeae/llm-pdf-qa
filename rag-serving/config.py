from urllib.parse import urlparse

from shared.config import SharedSettings


class ServingSettings(SharedSettings):
    # Web Search
    web_search_enabled: bool = True
    google_api_key: str = ""
    google_cx: str = ""

    # Serving
    serving_api_port: int = 8002
    frontend_port: int = 3000
    prefer_env_llm_config: bool = True
    cors_allow_origins: str = ""
    next_public_api_url: str = ""
    fallback_system_prompt: str = (
        "당신은 사내 문서를 기반으로 답변하는 AI 어시스턴트입니다. "
        "제공된 문서 내용을 바탕으로 정확하고 도움이 되는 답변을 제공하세요."
    )
    fallback_max_tokens: int = 4096
    fallback_temperature: float = 0.7
    fallback_top_p: float = 0.9
    fallback_context_chunks: int = 5
    retrieval_context_expansion_factor: int = 4
    retrieval_min_limit: int = 20
    retrieval_max_candidates: int = 60
    retrieval_base_candidate_multiplier: int = 2
    retrieval_intent_candidate_multiplier: int = 3
    retrieval_focused_limit_multiplier: int = 2
    retrieval_focused_min_limit: int = 12
    rerank_model_weight: float = 0.55
    rerank_prior_weight: float = 0.30
    rerank_feature_weight: float = 0.15
    rerank_mmr_enabled: bool = True
    rerank_mmr_lambda: float = 0.7
    retrieval_budget_general: str = ""
    retrieval_budget_table: str = "table:8,caption:4,text:8"
    retrieval_budget_image: str = "image:8,caption:6,text:6"
    retrieval_budget_caption: str = "caption:8,image:4,table:4,text:4"
    retrieval_budget_slide: str = "text:10,caption:4,table:4"
    retrieval_budget_page: str = "text:10,table:4,caption:4"

    @property
    def cors_origins(self) -> list[str]:
        origins = {
            f"http://localhost:{self.frontend_port}",
            f"http://127.0.0.1:{self.frontend_port}",
        }

        if self.cors_allow_origins:
            for origin in self.cors_allow_origins.split(","):
                normalized = origin.strip().rstrip("/")
                if normalized:
                    origins.add(normalized)

        api_url = self.next_public_api_url.strip()
        if api_url:
            try:
                parsed = urlparse(api_url)
                if parsed.scheme and parsed.hostname:
                    inferred_origin = f"{parsed.scheme}://{parsed.hostname}:{self.frontend_port}"
                    origins.add(inferred_origin)
            except ValueError:
                pass

        return sorted(origins)

    @property
    def retrieval_budgets(self) -> dict[str, dict[str, int]]:
        raw_budgets = {
            "general": self.retrieval_budget_general,
            "table": self.retrieval_budget_table,
            "image": self.retrieval_budget_image,
            "caption": self.retrieval_budget_caption,
            "slide": self.retrieval_budget_slide,
            "page": self.retrieval_budget_page,
        }

        parsed: dict[str, dict[str, int]] = {}
        for intent, raw_value in raw_budgets.items():
            budget: dict[str, int] = {}
            for item in raw_value.split(","):
                key, sep, value = item.partition(":")
                key = key.strip()
                value = value.strip()
                if not sep or not key or not value:
                    continue
                try:
                    budget[key] = int(value)
                except ValueError:
                    continue
            parsed[intent] = budget
        return parsed

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


serving_settings = ServingSettings()
