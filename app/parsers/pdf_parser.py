import logging
from functools import lru_cache

import httpx

from app.config import settings
from app.parsers.base import BaseParser, ParseResult, ParsedPage

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_http_client() -> httpx.Client:
    # Reuse keep-alive connections to reduce per-request overhead.
    return httpx.Client()


class PdfParser(BaseParser):
    SUPPORTED_EXTENSIONS = [".pdf"]

    def parse(self, file_path: str) -> ParseResult:
        """Parse PDF by calling MinerU API service."""
        response = _get_http_client().post(
            f"{settings.mineru_api_url}/parse",
            json={
                "file_path": file_path,
                "method": "auto",
                "backend": settings.mineru_backend,
                "lang": settings.mineru_lang,
            },
            timeout=600.0,
        )

        if response.status_code != 200:
            detail = response.json().get("detail", response.text)
            raise RuntimeError(f"MinerU API error for {file_path}: {detail}")

        data = response.json()

        pages = [
            ParsedPage(page_num=p["page_num"], text=p["text"])
            for p in data["pages"]
        ]

        return ParseResult(
            pages=pages,
            raw_text=data["markdown"],
            total_pages=data["total_pages"],
            metadata=data["metadata"],
        )
