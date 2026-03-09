"""Document parser module.

Delegates to MinerU API for PDF/image parsing, falls back to local parsers
for DOCX, XLSX, PPTX.
"""

import logging
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import httpx

from rag_pipeline.config import pipeline_settings

logger = logging.getLogger(__name__)


@dataclass
class ExtractedImage:
    temp_path: str
    page_num: int | None
    image_type: str
    width: int | None = None
    height: int | None = None


@dataclass
class ParseResult:
    raw_text: str
    images: list[ExtractedImage] = field(default_factory=list)
    total_pages: int = 0
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# MinerU API client (PDF + image OCR)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_http_client() -> httpx.Client:
    return httpx.Client()


MINERU_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
LOCAL_EXTENSIONS = {".docx", ".xlsx", ".xls", ".pptx"}


def parse_document(file_path: str) -> ParseResult:
    """Parse a document, routing to the appropriate parser."""
    ext = Path(file_path).suffix.lower()

    if ext in MINERU_EXTENSIONS:
        return _parse_via_mineru(file_path, ext)
    elif ext == ".docx":
        return _parse_docx(file_path)
    elif ext in (".xlsx", ".xls"):
        return _parse_xlsx(file_path)
    elif ext == ".pptx":
        return _parse_pptx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


# ---------------------------------------------------------------------------
# MinerU API
# ---------------------------------------------------------------------------

def _parse_via_mineru(file_path: str, ext: str) -> ParseResult:
    """Call the MinerU API microservice."""
    method = "ocr" if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff") else "auto"
    timeout = 300.0 if method == "ocr" else 600.0

    response = _get_http_client().post(
        f"{pipeline_settings.mineru_api_url}/parse",
        json={
            "file_path": file_path,
            "method": method,
            "backend": pipeline_settings.mineru_backend,
            "lang": pipeline_settings.mineru_lang,
        },
        timeout=timeout,
    )

    if response.status_code != 200:
        detail = response.json().get("detail", response.text)
        raise RuntimeError(f"MinerU API error for {file_path}: {detail}")

    data = response.json()

    images = [
        ExtractedImage(
            temp_path=img["path"],
            page_num=None,
            image_type=Path(img["path"]).suffix.lstrip("."),
        )
        for img in data.get("images", [])
    ]

    return ParseResult(
        raw_text=data["markdown"],
        images=images,
        total_pages=data["total_pages"],
        metadata=data.get("metadata", {}),
    )


# ---------------------------------------------------------------------------
# Local parsers (DOCX, XLSX, PPTX)
# ---------------------------------------------------------------------------

def _parse_docx(file_path: str) -> ParseResult:
    """Parse DOCX using python-docx."""
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn

    doc = DocxDocument(file_path)
    extracted_images: list[ExtractedImage] = []
    parts = []
    image_count = 0

    for element in doc.element.body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

        if tag == "p":
            runs_text = []
            for run in element.iter(qn("w:r")):
                t = run.find(qn("w:t"))
                if t is not None and t.text:
                    runs_text.append(t.text)
                drawing = run.find(qn("w:drawing"))
                if drawing is not None:
                    image_count += 1
                    # Extract image blob if possible
                    img = _extract_docx_inline_image(doc, drawing, image_count, extracted_images)
                    if img:
                        runs_text.append(img)

            text = "".join(runs_text).strip()
            if text:
                parts.append(text)

        elif tag == "tbl":
            table_md = _docx_table_to_markdown(element, qn)
            if table_md:
                parts.append(table_md)

    # Extract all embedded images from relationships
    for rel in doc.part.rels.values():
        if "image" in rel.reltype:
            try:
                blob = rel.target_part.blob
                ext = "png"
                with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                    tmp.write(blob)
                    extracted_images.append(ExtractedImage(
                        temp_path=tmp.name,
                        page_num=1,
                        image_type=ext,
                    ))
            except Exception as e:
                logger.debug("Failed to extract image from relationship: %s", e)

    full_text = "\n\n".join(parts)

    if not full_text.strip():
        full_text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

    return ParseResult(
        raw_text=full_text,
        images=extracted_images,
        total_pages=1,
        metadata={"parser": "python-docx", "source": file_path, "image_count": image_count},
    )


def _extract_docx_inline_image(doc, drawing_element, img_idx, extracted_images):
    """Try to extract inline image from a drawing element."""
    from docx.oxml.ns import qn

    try:
        blip = drawing_element.find(".//" + qn("a:blip"))
        if blip is None:
            return f"[image {img_idx}]"
        embed_id = blip.get(qn("r:embed"))
        if not embed_id:
            return f"[image {img_idx}]"
        rel = doc.part.rels.get(embed_id)
        if rel is None:
            return f"[image {img_idx}]"
        blob = rel.target_part.blob
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(blob)
            extracted_images.append(ExtractedImage(
                temp_path=tmp.name,
                page_num=1,
                image_type="png",
            ))
        return f"[image {img_idx}]"
    except Exception as e:
        logger.debug("Failed to extract inline image %d: %s", img_idx, e)
        return f"[image {img_idx}]"


def _docx_table_to_markdown(tbl_element, qn) -> str:
    """Convert lxml table element to markdown table."""
    rows = []
    for tr in tbl_element.iter(qn("w:tr")):
        cells = []
        for tc in tr.iter(qn("w:tc")):
            cell_texts = []
            for p in tc.iter(qn("w:p")):
                t_parts = []
                for t in p.iter(qn("w:t")):
                    if t.text:
                        t_parts.append(t.text)
                cell_texts.append("".join(t_parts))
            cells.append(" ".join(cell_texts).strip())
        rows.append(cells)

    if not rows:
        return ""

    lines = []
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
    for row in rows[1:]:
        while len(row) < len(rows[0]):
            row.append("")
        lines.append("| " + " | ".join(row[:len(rows[0])]) + " |")

    return "\n".join(lines)


def _parse_xlsx(file_path: str) -> ParseResult:
    """Parse XLSX/XLS using openpyxl."""
    from openpyxl import load_workbook

    wb = load_workbook(file_path, read_only=True, data_only=True)
    all_texts = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            cell_values = [str(c) if c is not None else "" for c in row]
            if any(v.strip() for v in cell_values):
                rows.append(" | ".join(cell_values))

        if rows:
            sheet_text = f"## Sheet: {sheet_name}\n\n" + "\n".join(rows)
            all_texts.append(sheet_text)

    wb.close()
    full_text = "\n\n".join(all_texts)

    return ParseResult(
        raw_text=full_text,
        total_pages=len(all_texts) or 1,
        metadata={"parser": "openpyxl", "source": file_path},
    )


def _parse_pptx(file_path: str) -> ParseResult:
    """Parse PPTX using python-pptx."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(file_path)
    extracted_images: list[ExtractedImage] = []
    all_texts = []

    for slide_idx, slide in enumerate(prs.slides):
        parts = []

        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    parts.append(text)

            if shape.has_table:
                table_md = _pptx_table_to_markdown(shape.table)
                if table_md:
                    parts.append(table_md)

            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    image = shape.image
                    blob = image.blob
                    ext = image.content_type.split("/")[-1]
                    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                        tmp.write(blob)
                        extracted_images.append(ExtractedImage(
                            temp_path=tmp.name,
                            page_num=slide_idx + 1,
                            image_type=ext,
                        ))
                except Exception as e:
                    logger.debug("Failed to extract image on slide %d: %s", slide_idx + 1, e)

            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                for child in shape.shapes:
                    if hasattr(child, "text") and child.text.strip():
                        parts.append(child.text.strip())
                    if hasattr(child, "has_table") and child.has_table:
                        table_md = _pptx_table_to_markdown(child.table)
                        if table_md:
                            parts.append(table_md)

        if parts:
            slide_text = f"## Slide {slide_idx + 1}\n\n" + "\n\n".join(parts)
            all_texts.append(slide_text)

    full_text = "\n\n".join(all_texts)

    return ParseResult(
        raw_text=full_text,
        images=extracted_images,
        total_pages=len(prs.slides),
        metadata={"parser": "python-pptx", "source": file_path, "slide_count": len(prs.slides)},
    )


def _pptx_table_to_markdown(table) -> str:
    """Convert pptx Table to markdown."""
    rows = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append(cells)

    if not rows:
        return ""

    col_count = len(rows[0])
    lines = []
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    for row in rows[1:]:
        while len(row) < col_count:
            row.append("")
        lines.append("| " + " | ".join(row[:col_count]) + " |")

    return "\n".join(lines)
