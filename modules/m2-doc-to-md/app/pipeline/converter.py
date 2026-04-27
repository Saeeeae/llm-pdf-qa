import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

KORDOC_BIN = os.getenv("KORDOC_BIN", "kordoc")
KORDOC_EXTS = {".pdf", ".docx", ".xlsx", ".xls", ".hwp", ".hwpx"}


def _frontmatter(rel_path: str, file_hash: str, fmt: str) -> str:
    return (
        "---\n"
        f"source_path: {rel_path}\n"
        f"source_hash: {file_hash}\n"
        f"format: {fmt}\n"
        f"converted_at: {datetime.now(timezone.utc).isoformat()}\n"
        "---\n\n"
    )


def _run_kordoc(src: Path) -> str:
    bin_ = shutil.which(KORDOC_BIN) or KORDOC_BIN
    result = subprocess.run(
        [bin_, "--silent", str(src)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"kordoc failed: {result.stderr.strip()}")
    return result.stdout


def _run_pptx(src: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(src))
    parts = []
    for i, slide in enumerate(prs.slides, 1):
        parts.append(f"## Slide {i}")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = "".join(r.text for r in para.runs).strip()
                    if text:
                        parts.append(text)
        parts.append("")
    return "\n".join(parts)


def convert(src: Path, rel_path: str, file_hash: str, out_dir: Path) -> tuple[Path, str]:
    """Convert document to Markdown. Returns (md_path, status)."""
    ext = src.suffix.lower()
    fmt = ext.lstrip(".")
    md_path = out_dir / (rel_path.rsplit(".", 1)[0] + ".md")
    md_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if ext in KORDOC_EXTS:
            body = _run_kordoc(src)
            status = "ok"
        elif ext == ".pptx":
            body = _run_pptx(src)
            status = "ok-pptx-fallback"
        else:
            raise ValueError(f"unsupported ext: {ext}")
    except Exception as e:
        body = f"<!-- conversion failed: {e} -->\n"
        status = f"fail:{type(e).__name__}"

    md_path.write_text(_frontmatter(rel_path, file_hash, fmt) + body, encoding="utf-8")
    return md_path, status
