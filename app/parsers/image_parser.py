import logging
import subprocess
import tempfile
from pathlib import Path

from app.config import settings
from app.parsers.base import BaseParser, ParseResult, ParsedPage

logger = logging.getLogger(__name__)


class ImageParser(BaseParser):
    SUPPORTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tif", ".tiff"]

    def parse(self, file_path: str) -> ParseResult:
        """Parse image using MinerU v2.x OCR.

        First tries Python API, falls back to CLI.
        """
        try:
            return self._parse_via_api(file_path)
        except ImportError:
            logger.info("MinerU Python API not available, falling back to CLI")
            return self._parse_via_cli(file_path)

    def _parse_via_api(self, file_path: str) -> ParseResult:
        from mineru.demo.demo import parse_doc

        with tempfile.TemporaryDirectory() as tmpdir:
            parse_doc(
                path_list=[Path(file_path)],
                output_dir=tmpdir,
                lang=settings.mineru_lang,
                backend=settings.mineru_backend,
                method="ocr",
            )
            return self._read_output(file_path, tmpdir)

    def _parse_via_cli(self, file_path: str) -> ParseResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "mineru",
                    "-p", file_path,
                    "-o", tmpdir,
                    "-m", "ocr",
                    "-b", settings.mineru_backend,
                    "-l", settings.mineru_lang,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.error("MinerU OCR CLI failed: %s", result.stderr)
                raise RuntimeError(
                    f"MinerU OCR failed for {file_path}: {result.stderr[:500]}"
                )
            return self._read_output(file_path, tmpdir)

    def _read_output(self, file_path: str, output_dir: str) -> ParseResult:
        md_files = list(Path(output_dir).rglob("*.md"))
        if not md_files:
            raise FileNotFoundError(
                f"No markdown output from MinerU OCR for {file_path}"
            )

        md_text = md_files[0].read_text(encoding="utf-8")
        pages = [ParsedPage(page_num=1, text=md_text.strip())]

        return ParseResult(
            pages=pages,
            raw_text=md_text,
            total_pages=1,
            metadata={
                "parser": "mineru-ocr",
                "backend": settings.mineru_backend,
                "source": file_path,
            },
        )
