import logging

import httpx

from app.config import settings
from app.parsers.base import BaseParser, ParseResult, ParsedPage

logger = logging.getLogger(__name__)


class ImageParser(BaseParser):
    SUPPORTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tif", ".tiff"]

    def parse(self, file_path: str) -> ParseResult:
        """Parse image by calling MinerU API service (OCR mode)."""
        response = httpx.post(
            f"{settings.mineru_api_url}/parse",
            json={
                "file_path": file_path,
                "method": "ocr",
                "backend": settings.mineru_backend,
                "lang": settings.mineru_lang,
            },
            timeout=300.0,
        )

        if response.status_code != 200:
            detail = response.json().get("detail", response.text)
            raise RuntimeError(f"MinerU OCR API error for {file_path}: {detail}")

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
