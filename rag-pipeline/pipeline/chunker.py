"""Text chunking module.

Adapted from app/processing/chunker.py for the v2 monorepo structure.
Uses rag_pipeline.config instead of app.config.
"""

import logging
import re
from functools import lru_cache
from typing import TYPE_CHECKING

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:  # pragma: no cover - exercised in lightweight test/dev envs
    RecursiveCharacterTextSplitter = None

from rag_pipeline.config import pipeline_settings

if TYPE_CHECKING:
    from rag_pipeline.pipeline.parser import ParseBlock

logger = logging.getLogger(__name__)

PAGE_BREAK_RE = re.compile(r"^\s*-{3,}\s*$")
HEADING_RE = re.compile(r"^\s*(#{1,6}\s+\S+|(?:\d+(?:\.\d+){0,3}[\.)])\s+\S+)\s*$")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")


@lru_cache(maxsize=1)
def _get_tokenizer():
    from shared.config import shared_settings
    if shared_settings.smoke_test_mode:
        return None
    try:
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(shared_settings.embedding_model_name)
    except Exception as exc:
        logger.warning("Falling back to approximate token counting: %s", exc)
        return None


def token_length(text: str) -> int:
    tokenizer = _get_tokenizer()
    if tokenizer is None:
        stripped = text.strip()
        if not stripped:
            return 0
        # Mixed ko/en approximation for smoke/dev mode.
        return max(1, len(stripped) // 4)
    return len(tokenizer.encode(text, add_special_tokens=False))


def _split_structural_sections(text: str) -> list[str]:
    """Split text by structural cues (headings, paragraph breaks, page breaks)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections: list[str] = []
    buffer: list[str] = []

    def flush_buffer():
        if not buffer:
            return
        section = "\n".join(buffer).strip()
        if section:
            sections.append(section)
        buffer.clear()

    for line in lines:
        stripped = line.strip()

        if PAGE_BREAK_RE.match(stripped):
            flush_buffer()
            continue

        if HEADING_RE.match(stripped):
            flush_buffer()
            sections.append(stripped)
            continue

        if not stripped:
            flush_buffer()
            continue

        # Keep markdown tables intact as a single structural region.
        if TABLE_RE.match(stripped):
            buffer.append(stripped)
            continue

        buffer.append(line.rstrip())

    flush_buffer()
    return sections


def _merge_small_sections(sections: list[str], min_tokens: int) -> list[str]:
    """Merge tiny sections to reduce over-fragmentation in semantic chunking."""
    if min_tokens <= 0:
        return sections

    merged: list[str] = []
    carry: list[str] = []

    def flush_carry(force: bool = False):
        if not carry:
            return
        carry_text = "\n\n".join(carry).strip()
        if not carry_text:
            carry.clear()
            return

        if force or token_length(carry_text) >= min_tokens:
            merged.append(carry_text)
            carry.clear()

    for section in sections:
        section = section.strip()
        if not section:
            continue

        section_tokens = token_length(section)
        if section_tokens >= min_tokens and not carry:
            merged.append(section)
            continue

        carry.append(section)
        flush_carry()

    if carry:
        tail = "\n\n".join(carry).strip()
        if merged and token_length(tail) < min_tokens:
            merged[-1] = f"{merged[-1]}\n\n{tail}"
        elif tail:
            merged.append(tail)

    return merged


def _split_by_tokens(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if RecursiveCharacterTextSplitter is None:
        words = text.split()
        if not words:
            return []

        chunks: list[str] = []
        step = max(1, chunk_size - chunk_overlap)
        start = 0
        while start < len(words):
            window = words[start:start + chunk_size]
            if not window:
                break
            chunks.append(" ".join(window))
            start += step
        return chunks

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=token_length,
        separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""],
    )
    return splitter.split_text(text)


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    strategy: str | None = None,
) -> list[dict]:
    """Split text into chunks with token-based or hybrid strategy.

    Returns list of {"text": str, "token_cnt": int, "chunk_idx": int}.
    """
    if not text or not text.strip():
        return []

    chunk_size = chunk_size or pipeline_settings.chunk_size
    chunk_overlap = chunk_overlap or pipeline_settings.chunk_overlap
    strategy = (strategy or pipeline_settings.chunk_strategy).lower().strip()
    min_tokens = pipeline_settings.chunk_min_section_tokens

    if strategy == "token":
        sections = [text.strip()]
    elif strategy == "hybrid":
        sections = _split_structural_sections(text)
        sections = _merge_small_sections(sections, min_tokens=min_tokens)
    else:
        logger.warning("Unknown chunk_strategy=%s. Falling back to hybrid.", strategy)
        sections = _merge_small_sections(_split_structural_sections(text), min_tokens=min_tokens)

    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue

        if token_length(section) <= chunk_size:
            chunks.append(section)
            continue

        chunks.extend(_split_by_tokens(section, chunk_size=chunk_size, chunk_overlap=chunk_overlap))

    return [
        {
            "text": c,
            "token_cnt": token_length(c),
            "chunk_idx": i,
        }
        for i, c in enumerate(chunks)
    ]


def chunk_parse_blocks(
    blocks: list["ParseBlock"],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[dict]:
    """Chunk parser blocks while preserving multimodal metadata."""
    if not blocks:
        return []

    chunk_size = chunk_size or pipeline_settings.chunk_size
    chunk_overlap = chunk_overlap or pipeline_settings.chunk_overlap

    items: list[dict] = []
    chunk_idx = 0

    for block_idx, block in enumerate(blocks):
        text = (block.source_text or "").strip()
        if not text:
            continue

        if token_length(text) <= chunk_size:
            parts = [text]
        else:
            parts = _split_by_tokens(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        for part in parts:
            content = part.strip()
            if not content:
                continue

            items.append(
                {
                    "text": content,
                    "token_cnt": token_length(content),
                    "chunk_idx": chunk_idx,
                    "chunk_type": block.block_type,
                    "page_number": block.page_number,
                    "sheet_name": block.sheet_name,
                    "slide_number": block.slide_number,
                    "section_path": block.section_path,
                    "language": block.language,
                    "block_idx": block_idx,
                }
            )
            chunk_idx += 1

    return items
