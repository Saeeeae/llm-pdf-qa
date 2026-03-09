from shared.config import SharedSettings


class PipelineSettings(SharedSettings):
    # MinerU
    mineru_api_url: str = "http://mineru-api:9000"
    mineru_backend: str = "hybrid-auto-engine"
    mineru_lang: str = "korean"

    # Scanning
    source_scan_paths: str = "/mnt/nas/documents"

    # Chunking
    chunk_strategy: str = "hybrid"
    chunk_size: int = 512
    chunk_overlap: int = 50
    chunk_min_section_tokens: int = 80

    # Image
    enable_image_embedding: bool = True
    image_store_dir: str = "/data/images"

    # API
    pipeline_api_port: int = 8001

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


pipeline_settings = PipelineSettings()
