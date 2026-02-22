import logging
import tempfile
from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.ns import qn

from app.parsers.base import BaseParser, ParseResult, ParsedPage

logger = logging.getLogger(__name__)


class DocxParser(BaseParser):
    SUPPORTED_EXTENSIONS = [".docx"]

    def parse(self, file_path: str) -> ParseResult:
        doc = DocxDocument(file_path)

        # 문서 body의 요소를 순서대로 처리 (paragraph, table, image 혼재)
        parts = []
        image_count = 0

        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                # Paragraph - 텍스트 + 인라인 이미지 처리
                # 전체 텍스트를 재구성 (run 단위)
                runs_text = []
                for run in element.iter(qn("w:r")):
                    t = run.find(qn("w:t"))
                    if t is not None and t.text:
                        runs_text.append(t.text)
                    # 인라인 이미지 감지
                    drawing = run.find(qn("w:drawing"))
                    if drawing is not None:
                        image_count += 1
                        img_text = self._extract_image_ocr(doc, drawing, image_count)
                        if img_text:
                            runs_text.append(img_text)

                text = "".join(runs_text).strip()
                if text:
                    parts.append(text)

            elif tag == "tbl":
                # Table → 마크다운 표로 변환
                table_md = self._table_to_markdown(element)
                if table_md:
                    parts.append(table_md)

        # 이미지가 relationship에도 있을 수 있으므로, 별도로 추출
        embedded_images = self._extract_all_images(doc)
        if embedded_images:
            parts.append(f"\n[문서 내 이미지 {len(embedded_images)}개 포함]")
            for idx, img_text in enumerate(embedded_images, 1):
                if img_text:
                    parts.append(f"### 이미지 {idx}\n{img_text}")

        full_text = "\n\n".join(parts)

        if not full_text.strip():
            # fallback: 단순 텍스트 추출
            full_text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

        pages = [ParsedPage(page_num=1, text=full_text)]

        return ParseResult(
            pages=pages,
            raw_text=full_text,
            total_pages=1,
            metadata={
                "parser": "python-docx",
                "source": file_path,
                "image_count": image_count,
            },
        )

    def _table_to_markdown(self, tbl_element) -> str:
        """lxml table element → 마크다운 표."""
        rows = []
        for tr in tbl_element.iter(qn("w:tr")):
            cells = []
            for tc in tr.iter(qn("w:tc")):
                # 셀 내 모든 텍스트 합치기
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

        # 마크다운 표 생성
        lines = []
        # 헤더
        lines.append("| " + " | ".join(rows[0]) + " |")
        lines.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
        # 데이터
        for row in rows[1:]:
            # 열 수 맞추기
            while len(row) < len(rows[0]):
                row.append("")
            lines.append("| " + " | ".join(row[:len(rows[0])]) + " |")

        return "\n".join(lines)

    def _extract_image_ocr(self, doc, drawing_element, img_idx: int) -> str:
        """인라인 이미지에서 OCR 텍스트 추출 시도."""
        try:
            blip = drawing_element.find(".//" + qn("a:blip"))
            if blip is None:
                return f"[이미지 {img_idx}]"

            embed_id = blip.get(qn("r:embed"))
            if not embed_id:
                return f"[이미지 {img_idx}]"

            rel = doc.part.rels.get(embed_id)
            if rel is None:
                return f"[이미지 {img_idx}]"

            image_blob = rel.target_part.blob
            return self._ocr_image_blob(image_blob, img_idx)
        except Exception as e:
            logger.debug("Failed to extract image %d: %s", img_idx, e)
            return f"[이미지 {img_idx}]"

    def _extract_all_images(self, doc) -> list[str]:
        """문서 내 모든 이미지를 추출하여 OCR."""
        results = []
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                try:
                    blob = rel.target_part.blob
                    text = self._ocr_image_blob(blob, len(results) + 1)
                    if text and not text.startswith("[이미지"):
                        results.append(text)
                except Exception as e:
                    logger.debug("Failed to extract image from relationship: %s", e)
        return results

    def _ocr_image_blob(self, blob: bytes, img_idx: int) -> str:
        """이미지 바이트 → MinerU OCR 텍스트 (실패 시 placeholder)."""
        try:
            from app.parsers.image_parser import ImageParser

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(blob)
                tmp_path = tmp.name

            parser = ImageParser()
            result = parser.parse(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)

            if result.raw_text.strip():
                return result.raw_text.strip()
        except Exception as e:
            logger.debug("OCR failed for embedded image %d: %s", img_idx, e)

        return f"[이미지 {img_idx}]"
