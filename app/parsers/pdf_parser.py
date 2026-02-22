import logging
import subprocess
import tempfile
from pathlib import Path

from app.config import settings
from app.parsers.base import BaseParser, ParseResult, ParsedPage

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    SUPPORTED_EXTENSIONS = [".pdf"]

    def parse(self, file_path: str) -> ParseResult:
        """Parse PDF using MinerU v2.x.

        First tries Python API (parse_doc), falls back to CLI (mineru).
        """
        try:
            return self._parse_via_api(file_path)
        except ImportError:
            logger.info("MinerU Python API not available, falling back to CLI")
            return self._parse_via_cli(file_path)

    def _parse_via_api(self, file_path: str) -> ParseResult:
        """Use MinerU Python API directly."""
        from mineru.demo.demo import parse_doc

        with tempfile.TemporaryDirectory() as tmpdir:
            parse_doc(
                path_list=[Path(file_path)],
                output_dir=tmpdir,
                lang=settings.mineru_lang,
                backend=settings.mineru_backend,
                method="auto",
            )
            return self._read_output(file_path, tmpdir)

    def _parse_via_cli(self, file_path: str) -> ParseResult:
        """Fallback: use MinerU CLI (mineru command)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "mineru",
                    "-p", file_path,
                    "-o", tmpdir,
                    "-m", "auto",
                    "-b", settings.mineru_backend,
                    "-l", settings.mineru_lang,
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                logger.error("MinerU CLI failed: %s", result.stderr)
                raise RuntimeError(
                    f"MinerU failed for {file_path}: {result.stderr[:500]}"
                )
            return self._read_output(file_path, tmpdir)

    def _read_output(self, file_path: str, output_dir: str) -> ParseResult:
        """Read markdown output from MinerU output directory."""
        stem = Path(file_path).stem
        output_path = Path(output_dir)

        # MinerU v2.x output structure varies by version
        candidate_paths = [
            output_path / stem / "auto" / f"{stem}.md",
            output_path / stem / settings.mineru_backend / f"{stem}.md",
            output_path / stem / f"{stem}.md",
        ]

        md_path = None
        for p in candidate_paths:
            if p.exists():
                md_path = p
                break

        if md_path is None:
            md_files = list(output_path.rglob("*.md"))
            if md_files:
                md_path = md_files[0]
            else:
                raise FileNotFoundError(
                    f"No markdown output from MinerU for {file_path}"
                )

        md_text = md_path.read_text(encoding="utf-8")

        # Split by page break markers if present
        page_marker = "\n---\n"
        if page_marker in md_text:
            page_texts = md_text.split(page_marker)
        else:
            page_texts = [md_text]

        pages = [
            ParsedPage(page_num=i + 1, text=text.strip())
            for i, text in enumerate(page_texts)
            if text.strip()
        ]

        return ParseResult(
            pages=pages,
            raw_text=md_text,
            total_pages=len(pages),
            metadata={
                "parser": "mineru",
                "backend": settings.mineru_backend,
                "source": file_path,
            },
        )
