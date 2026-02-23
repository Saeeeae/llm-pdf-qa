"""MinerU Parsing Microservice.

Standalone FastAPI server that wraps MinerU for PDF/image parsing.
Called by the main worker via HTTP instead of importing MinerU directly.
"""

import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="MinerU Parsing API", version="1.0.0")

# Configuration from environment
MINERU_BACKEND = os.environ.get("MINERU_BACKEND", "pipeline")
MINERU_LANG = os.environ.get("MINERU_LANG", "korean")


class ParseRequest(BaseModel):
    file_path: str
    method: str = "auto"  # "auto" for PDF, "ocr" for images
    backend: str | None = None
    lang: str | None = None


class ParseResponse(BaseModel):
    markdown: str
    total_pages: int
    pages: list[dict]  # [{"page_num": 1, "text": "..."}, ...]
    metadata: dict


@app.get("/health")
def health():
    return {"status": "ok", "service": "mineru-api"}


@app.post("/parse", response_model=ParseResponse)
def parse_document(req: ParseRequest):
    """Parse a document using MinerU.

    The file must be accessible from this container (shared volume).
    """
    file_path = req.file_path
    backend = req.backend or MINERU_BACKEND
    lang = req.lang or MINERU_LANG
    method = req.method

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    logger.info("Parsing %s (method=%s, backend=%s, lang=%s)", file_path, method, backend, lang)

    try:
        md_text, pages = _parse_with_mineru(file_path, method, backend, lang)
    except Exception as e:
        logger.error("MinerU parsing failed for %s: %s", file_path, e)
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)[:500]}")

    return ParseResponse(
        markdown=md_text,
        total_pages=len(pages),
        pages=[{"page_num": p["page_num"], "text": p["text"]} for p in pages],
        metadata={
            "parser": "mineru-ocr" if method == "ocr" else "mineru",
            "backend": backend,
            "source": file_path,
        },
    )


def _parse_with_mineru(file_path: str, method: str, backend: str, lang: str) -> tuple[str, list[dict]]:
    """Run MinerU and return (full_markdown, pages_list)."""
    try:
        return _parse_via_api(file_path, method, backend, lang)
    except ImportError:
        logger.info("MinerU Python API not available, falling back to CLI")
        return _parse_via_cli(file_path, method, backend, lang)


def _parse_via_api(file_path: str, method: str, backend: str, lang: str) -> tuple[str, list[dict]]:
    """Use MinerU Python API directly."""
    from mineru.demo.demo import parse_doc

    with tempfile.TemporaryDirectory() as tmpdir:
        parse_doc(
            path_list=[Path(file_path)],
            output_dir=tmpdir,
            lang=lang,
            backend=backend,
            method=method,
        )
        return _read_output(file_path, tmpdir)


def _parse_via_cli(file_path: str, method: str, backend: str, lang: str) -> tuple[str, list[dict]]:
    """Fallback: use MinerU CLI."""
    import subprocess

    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [
                "mineru",
                "-p", file_path,
                "-o", tmpdir,
                "-m", method,
                "-b", backend,
                "-l", lang,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"MinerU CLI failed: {result.stderr[:500]}")
        return _read_output(file_path, tmpdir)


def _read_output(file_path: str, output_dir: str) -> tuple[str, list[dict]]:
    """Read markdown output from MinerU output directory."""
    stem = Path(file_path).stem
    output_path = Path(output_dir)

    candidate_paths = [
        output_path / stem / "auto" / f"{stem}.md",
        output_path / stem / MINERU_BACKEND / f"{stem}.md",
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
            raise FileNotFoundError(f"No markdown output from MinerU for {file_path}")

    md_text = md_path.read_text(encoding="utf-8")

    page_marker = "\n---\n"
    if page_marker in md_text:
        page_texts = md_text.split(page_marker)
    else:
        page_texts = [md_text]

    pages = [
        {"page_num": i + 1, "text": text.strip()}
        for i, text in enumerate(page_texts)
        if text.strip()
    ]

    return md_text, pages
