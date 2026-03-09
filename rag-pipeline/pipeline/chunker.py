"""Text chunking module.

Adapted from app/processing/chunker.py for the v2 monorepo structure.
Uses rag_pipeline.config instead of app.config.
"""

import logging
import re
from functools import lru_cache

from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

from rag_pipeline.config import pipeline_settings

logger = logging.getLogger(__name__)

PAGE_BREAK_RE = re.compile(r"^\s*-{3,}\s*$")
HEADING_RE = re.compile(r"^\s*(#{1,6}\s+\S+|(?:\d+(?:\.\d+){0,3}[\.)])\s+\S+)\s*$")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")


@lru_cache(maxsize=1)
def _get_tokenizer():
    from shared.config import shared_settings
    return AutoTokenizer.from_pretrained(shared_settings.embedding_model_name)


def token_length(text: str) -> int:
    tokenizer = _get_tokenizer()
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
