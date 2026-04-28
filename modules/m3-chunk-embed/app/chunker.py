"""Hierarchical, heading- and sentence-aware chunker.

Three layers:
1. **Section split** — break on Markdown ATX headings (`#`, `##`, ...). Each
   section carries a heading_path like "정책 > 휴가 > 신입사원" so chunks know
   where they came from.
2. **Sentence pack** — within each section, sentences are joined respecting
   Korean / English / CJK punctuation, then packed greedily into chunks up to
   the token budget. This avoids breaking mid-sentence.
3. **Hierarchical chunks** — produce parent (~PARENT_CHUNK_SIZE) and leaf
   (~LEAF_SIZE) chunks. Each leaf points to the parent containing its midpoint
   in token space; both inherit the section's heading_path.

Returns `(parents, leaves)` where each item carries `metadata = {"heading_path": "..."}`
plus the token-range fields. Downstream (m3 router) merges this with frontmatter.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

_MODEL_NAME = os.getenv("CHUNK_TOKENIZER", os.getenv("EMBED_MODEL", "BAAI/bge-m3"))

PARENT_SIZE = int(os.getenv("PARENT_CHUNK_SIZE", "1024"))
PARENT_OVERLAP = int(os.getenv("PARENT_CHUNK_OVERLAP", "100"))
LEAF_SIZE = int(os.getenv("CHUNK_SIZE", "256"))
LEAF_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "32"))

# Sentence terminators across English, CJK, Korean, and Japanese.
# Ends a sentence after one of: . ! ? 。 ！ ？ ． ？！ followed by whitespace,
# or after a hard newline. Greedy match keeps multi-punctuation ("?!") together.
_SENT_RE = re.compile(r"(?<=[.!?。！？．])\s+|(?<=[.!?。！？．])(?=[^\s.!?。！？．])|\n+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class ParentChunk:
    idx: int
    text: str
    start: int
    end: int
    metadata: dict = field(default_factory=dict)


@dataclass
class LeafChunk:
    idx: int
    text: str
    chunk_hash: str
    parent_idx: int
    start: int
    end: int
    metadata: dict = field(default_factory=dict)


@dataclass
class _Tmp:
    idx: int
    text: str
    start: int
    end: int


def split_sections(markdown: str) -> List[Tuple[str, str]]:
    """Split a markdown document into (heading_path, body) tuples.

    Maintains a heading-level stack so subheadings produce dotted paths like
    "1. 채용 > 1.1 신입". Body text before the first heading uses heading_path="".
    Code fences are honored — `#` inside ``` ``` blocks is not treated as a
    heading.
    """
    out: List[Tuple[str, str]] = []
    stack: List[str] = []
    current: List[str] = []
    in_fence = False

    def flush():
        if current and any(line.strip() for line in current):
            path = " > ".join(stack)
            out.append((path, "\n".join(current).strip()))

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence:
            m = _HEADING_RE.match(stripped)
            if m:
                flush()
                current = []
                level = len(m.group(1))
                title = m.group(2).strip()
                stack = stack[: level - 1] + [title]
                continue
        current.append(line)
    flush()
    if not out and markdown.strip():
        # No headings at all — single section with empty path.
        out.append(("", markdown.strip()))
    return out


def split_sentences(text: str) -> List[str]:
    """Korean/CJK/English-aware sentence splitter. Keeps short trailing sentences."""
    if not text:
        return []
    # Normalize multiple newlines to a single break so they act as boundaries.
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if p and p.strip()]


class Chunker:
    def __init__(
        self,
        model_name: str = _MODEL_NAME,
        parent_size: int = PARENT_SIZE,
        parent_overlap: int = PARENT_OVERLAP,
        leaf_size: int = LEAF_SIZE,
        leaf_overlap: int = LEAF_OVERLAP,
    ):
        if parent_size <= leaf_size:
            raise ValueError("parent_size must be > leaf_size")
        if parent_overlap >= parent_size or leaf_overlap >= leaf_size:
            raise ValueError("overlap must be < size")
        self.parent_size = parent_size
        self.parent_overlap = parent_overlap
        self.leaf_size = leaf_size
        self.leaf_overlap = leaf_overlap
        from transformers import AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(model_name)

    # ─── Public ─────────────────────────────────────────────────────────────
    def chunk(self, text: str) -> tuple[List[ParentChunk], List[LeafChunk]]:
        sections = split_sections(text)
        parents: List[ParentChunk] = []
        leaves: List[LeafChunk] = []
        if not sections:
            return parents, leaves

        for heading_path, body in sections:
            sect_parents, sect_leaves = self._chunk_section(
                body, heading_path,
                p_offset=len(parents),
                l_offset=len(leaves),
            )
            parents.extend(sect_parents)
            leaves.extend(sect_leaves)
        return parents, leaves

    # ─── Internal ───────────────────────────────────────────────────────────
    def _chunk_section(
        self,
        body: str,
        heading_path: str,
        p_offset: int,
        l_offset: int,
    ) -> Tuple[List[ParentChunk], List[LeafChunk]]:
        """Sentence-pack the section body, then carve into parent/leaf windows."""
        if not body.strip():
            return [], []

        sentences = split_sentences(body)
        if not sentences:
            sentences = [body]

        # Pre-tokenize each sentence once, then concat. Track sentence boundaries
        # in token space so packing can stop at a sentence end whenever possible.
        sent_ids = [self.tok.encode(s, add_special_tokens=False) for s in sentences]
        all_ids: List[int] = []
        sent_bounds: List[Tuple[int, int]] = []
        for ids in sent_ids:
            start = len(all_ids)
            all_ids.extend(ids)
            sent_bounds.append((start, len(all_ids)))

        if not all_ids:
            return [], []

        parents = self._slice_aware(
            all_ids, sent_bounds, self.parent_size, self.parent_overlap,
            offset=p_offset, heading_path=heading_path, kind="parent",
        )
        leaves_raw = self._slice_aware(
            all_ids, sent_bounds, self.leaf_size, self.leaf_overlap,
            offset=l_offset, heading_path=heading_path, kind="leaf",
        )

        # Re-shape leaf tmp objects into LeafChunks with parent_idx.
        leaves: List[LeafChunk] = []
        last_p = parents[-1].idx if parents else p_offset
        for tmp in leaves_raw:
            mid = (tmp.start + tmp.end) // 2
            parent_idx = last_p
            for p in parents:
                if p.start <= mid < p.end:
                    parent_idx = p.idx
                    break
            # Hash text alone collides across docs with shared boilerplate
            # (license footers, identical policy paragraphs). The router salts
            # this with doc_id at insert time, so the hash here is a content
            # fingerprint only — not the unique key persisted to the DB.
            h = hashlib.sha256(tmp.text.encode("utf-8")).hexdigest()
            leaves.append(
                LeafChunk(
                    idx=tmp.idx,
                    text=tmp.text,
                    chunk_hash=h,
                    parent_idx=parent_idx,
                    start=tmp.start,
                    end=tmp.end,
                    metadata={"heading_path": heading_path} if heading_path else {},
                )
            )
        return parents, leaves

    def _slice_aware(
        self,
        ids: List[int],
        sent_bounds: List[Tuple[int, int]],
        size: int,
        overlap: int,
        offset: int,
        heading_path: str,
        kind: str,
    ):
        """Slide a window of `size` tokens. Each window snaps its end to the
        nearest sentence boundary that does not overshoot, when possible.
        Falls back to a hard cut if a single sentence is longer than `size`.

        Yields ParentChunk for kind="parent", _Tmp for kind="leaf" (caller fills
        parent_idx/hash/metadata).
        """
        out = []
        idx = offset
        n = len(ids)
        if n == 0:
            return out

        # Map of sentence-end positions for fast lookup.
        sent_ends = [end for _, end in sent_bounds]

        cursor = 0
        while cursor < n:
            target_end = min(cursor + size, n)
            # Snap to the largest sentence boundary <= target_end (and > cursor).
            snapped_end = target_end
            for end in sent_ends:
                if cursor < end <= target_end:
                    snapped_end = end
            piece_ids = ids[cursor:snapped_end]
            if not piece_ids:
                break
            piece = self.tok.decode(piece_ids).strip()
            if piece:
                if kind == "parent":
                    out.append(
                        ParentChunk(
                            idx=idx,
                            text=piece,
                            start=cursor,
                            end=snapped_end,
                            metadata={"heading_path": heading_path} if heading_path else {},
                        )
                    )
                else:
                    out.append(
                        _Tmp(idx=idx, text=piece, start=cursor, end=snapped_end)
                    )
                idx += 1

            if snapped_end >= n:
                break
            # Advance with overlap; don't loop on no progress.
            next_cursor = max(snapped_end - overlap, cursor + 1)
            cursor = next_cursor
        return out
