"""MinerU Parsing Microservice.

Standalone FastAPI server that wraps MinerU for PDF/image parsing.
Called by the main worker via HTTP instead of importing MinerU directly.
"""

import logging
import os
import uuid
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
MINERU_OUTPUT_DIR = os.environ.get("MINERU_OUTPUT_DIR", "/tmp/mineru_output")


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
    images: list[dict] = []


def _create_output_dir(file_path: str) -> str:
    output_dir = os.path.join(MINERU_OUTPUT_DIR, f"{Path(file_path).stem}_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _summarize_output_dir(output_dir: str, max_entries: int = 40) -> str:
    output_path = Path(output_dir)
    if not output_path.exists():
        return "<missing>"

    entries: list[str] = []
    total_entries = 0
    for path in sorted(output_path.rglob("*")):
        total_entries += 1
        if len(entries) >= max_entries:
            continue
        rel_path = path.relative_to(output_path)
        try:
            suffix = "/" if path.is_dir() else f" ({path.stat().st_size}B)"
        except OSError:
            suffix = ""
        entries.append(f"{rel_path}{suffix}")

    if not entries:
        return "<empty>"
    if total_entries > len(entries):
        entries.append(f"... and {total_entries - len(entries)} more")
    return ", ".join(entries)


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
        md_text, pages, images, output_dir = _parse_with_mineru(file_path, method, backend, lang)
    except Exception as e:
        logger.exception("MinerU parsing failed for %s", file_path)
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)[:1500]}")

    return ParseResponse(
        markdown=md_text,
        total_pages=len(pages),
        pages=[{"page_num": p["page_num"], "text": p["text"]} for p in pages],
        images=images,
        metadata={
            "parser": "mineru-ocr" if method == "ocr" else "mineru",
            "backend": backend,
            "source": file_path,
            "mineru_output_dir": output_dir,
        },
    )


def _parse_with_mineru(file_path: str, method: str, backend: str, lang: str) -> tuple[str, list[dict], list[dict], str]:
    """Run MinerU and return (full_markdown, pages_list, images_list, output_dir)."""
    output_dir = _create_output_dir(file_path)
    logger.info("MinerU output directory prepared: %s", output_dir)

    api_error: Exception | None = None
    try:
        return _parse_via_api(file_path, method, backend, lang, output_dir)
    except ImportError as e:
        api_error = e
        logger.warning("MinerU Python API not available (%s), falling back to CLI", e)
    except Exception as e:
        api_error = e
        logger.exception(
            "MinerU Python API failed for %s; output_dir=%s; output_files=%s",
            file_path,
            output_dir,
            _summarize_output_dir(output_dir),
        )

    try:
        return _parse_via_cli(file_path, method, backend, lang, output_dir)
    except Exception as cli_error:
        output_summary = _summarize_output_dir(output_dir)
        if api_error is None:
            raise RuntimeError(
                f"MinerU parse failed for {file_path}. "
                f"cli_error={cli_error}. output_dir={output_dir}. output_files={output_summary}"
            ) from cli_error
        raise RuntimeError(
            f"MinerU parse failed for {file_path}. "
            f"api_error={api_error}. cli_error={cli_error}. "
            f"output_dir={output_dir}. output_files={output_summary}"
        ) from cli_error


def _parse_via_api(
    file_path: str,
    method: str,
    backend: str,
    lang: str,
    output_dir: str,
) -> tuple[str, list[dict], list[dict], str]:
    """Use MinerU Python API directly."""
    from mineru.demo.demo import parse_doc

    logger.info("Running MinerU Python API for %s -> %s", file_path, output_dir)
    parse_doc(
        path_list=[Path(file_path)],
        output_dir=output_dir,
        lang=lang,
        backend=backend,
        method=method,
    )
    logger.info(
        "MinerU Python API finished for %s; output_files=%s",
        file_path,
        _summarize_output_dir(output_dir),
    )
    md_text, pages, images = _read_output(file_path, output_dir, backend)
    return md_text, pages, images, output_dir


def _parse_via_cli(
    file_path: str,
    method: str,
    backend: str,
    lang: str,
    output_dir: str,
) -> tuple[str, list[dict], list[dict], str]:
    """Fallback: use MinerU CLI."""
    import subprocess

    logger.info("Running MinerU CLI for %s -> %s", file_path, output_dir)
    result = subprocess.run(
        [
            "mineru",
            "-p", file_path,
            "-o", output_dir,
            "-m", method,
            "-b", backend,
            "-l", lang,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.stdout:
        logger.debug("MinerU CLI stdout: %s", result.stdout[-1000:])
    if result.stderr:
        logger.debug("MinerU CLI stderr: %s", result.stderr[-1000:])
    if result.returncode != 0:
        raise RuntimeError(
            f"MinerU CLI failed (exit {result.returncode}) for {file_path}. "
            f"stderr_tail={result.stderr[-500:]}. stdout_tail={result.stdout[-500:]}. "
            f"output_dir={output_dir}. output_files={_summarize_output_dir(output_dir)}"
        )
    logger.info(
        "MinerU CLI finished for %s; output_files=%s",
        file_path,
        _summarize_output_dir(output_dir),
    )
    md_text, pages, images = _read_output(file_path, output_dir, backend)
    return md_text, pages, images, output_dir


def _read_output(file_path: str, output_dir: str, backend: str) -> tuple[str, list[dict], list[dict]]:
    """Read markdown output from MinerU output directory."""
    stem = Path(file_path).stem
    output_path = Path(output_dir)

    candidate_paths = [
        output_path / stem / "auto" / f"{stem}.md",
        output_path / stem / backend / f"{stem}.md",
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
                f"No markdown output from MinerU for {file_path}. "
                f"output_dir={output_dir}. output_files={_summarize_output_dir(output_dir)}"
            )

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

    # Collect images from images/ directory
    images = []
    image_files = []
    images_dir = md_path.parent / "images"
    if images_dir.is_dir():
        image_files.extend(sorted(images_dir.iterdir()))
    else:
        image_files.extend(sorted(output_path.rglob("*.png")))
        image_files.extend(sorted(output_path.rglob("*.jpg")))
        image_files.extend(sorted(output_path.rglob("*.jpeg")))

    for img_file in image_files:
        if img_file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'):
            images.append({
                "path": str(img_file),
                "filename": img_file.name,
            })

    return md_text, pages, images
