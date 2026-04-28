"""Hierarchical / heading-aware / sentence-aware chunker tests.

Bypasses the real tokenizer: each Unicode codepoint counts as one token id,
which keeps assertions on chunk boundaries deterministic.
"""
import hashlib

import pytest

from app.chunker import (
    Chunker,
    LeafChunk,
    ParentChunk,
    split_sections,
    split_sentences,
)


class _FakeTok:
    def encode(self, text, add_special_tokens=False):
        return [ord(c) for c in text]

    def decode(self, ids):
        return "".join(chr(i) for i in ids)


def _make_chunker(parent_size=20, parent_overlap=4, leaf_size=6, leaf_overlap=2):
    c = Chunker.__new__(Chunker)
    c.tok = _FakeTok()
    c.parent_size = parent_size
    c.parent_overlap = parent_overlap
    c.leaf_size = leaf_size
    c.leaf_overlap = leaf_overlap
    return c


# ─── Section split ────────────────────────────────────────────────────────
def test_split_sections_no_headings_single_section():
    out = split_sections("just some prose without headings.")
    assert len(out) == 1
    assert out[0][0] == ""  # empty heading_path
    assert "prose" in out[0][1]


def test_split_sections_basic_heading_path():
    md = "# A\nbody-a\n## B\nbody-b\n## C\nbody-c"
    out = split_sections(md)
    paths = [p for p, _ in out]
    assert paths == ["A", "A > B", "A > C"]


def test_split_sections_handles_code_fence():
    # `# Not a heading` lives inside a fenced code block and must NOT split.
    md = "# Real\nintro\n```\n# Not a heading\n```\n## Sub\nsubbody"
    out = split_sections(md)
    paths = [p for p, _ in out]
    assert paths == ["Real", "Real > Sub"]


def test_split_sections_empty_input():
    assert split_sections("") == []
    assert split_sections("   \n  \n") == []


# ─── Sentence split ───────────────────────────────────────────────────────
def test_split_sentences_english_basic():
    s = split_sentences("Hello world. How are you? I am fine!")
    assert len(s) == 3
    assert s[0].endswith(".")
    assert s[1].endswith("?")
    assert s[2].endswith("!")


def test_split_sentences_korean_punct():
    s = split_sentences("안녕하세요. 잘 지내시나요? 네! 감사합니다.")
    assert len(s) == 4


def test_split_sentences_cjk_full_stop():
    s = split_sentences("第一句。第二句。第三句")
    assert len(s) == 3


def test_split_sentences_newline_acts_as_boundary():
    s = split_sentences("A\nB\nC")
    assert s == ["A", "B", "C"]


# ─── Hierarchical chunking ────────────────────────────────────────────────
def test_chunk_empty_returns_empty():
    c = _make_chunker()
    parents, leaves = c.chunk("")
    assert parents == []
    assert leaves == []


def test_chunk_short_text_single_section():
    c = _make_chunker(parent_size=20, parent_overlap=4, leaf_size=6, leaf_overlap=2)
    parents, leaves = c.chunk("hi")
    assert len(parents) >= 1
    assert len(leaves) >= 1
    assert all(isinstance(p, ParentChunk) for p in parents)
    assert all(isinstance(leaf, LeafChunk) for leaf in leaves)


def test_chunk_long_text_multiple_chunks():
    c = _make_chunker(parent_size=10, parent_overlap=2, leaf_size=4, leaf_overlap=1)
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    parents, leaves = c.chunk(text)
    assert len(parents) >= 2
    assert len(leaves) > len(parents)


def test_chunk_with_headings_propagates_heading_path():
    c = _make_chunker(parent_size=20, parent_overlap=2, leaf_size=6, leaf_overlap=1)
    md = "# Top\nABCDEFGHIJ\n## Sub\nKLMNOPQR"
    parents, leaves = c.chunk(md)
    paths_p = {p.metadata.get("heading_path") for p in parents}
    paths_l = {leaf.metadata.get("heading_path") for leaf in leaves}
    # Both `Top` and `Top > Sub` should appear at parent and leaf level.
    assert "Top" in paths_p
    assert "Top > Sub" in paths_p
    assert "Top" in paths_l
    assert "Top > Sub" in paths_l


def test_chunk_leaf_hash_uniqueness():
    c = _make_chunker(parent_size=20, parent_overlap=2, leaf_size=4, leaf_overlap=0)
    _, leaves = c.chunk("abcdefghijklmnopqrstuvwxyz")
    hashes = [leaf.chunk_hash for leaf in leaves]
    assert len(hashes) == len(set(hashes))
    for leaf in leaves:
        assert leaf.chunk_hash == hashlib.sha256(leaf.text.encode()).hexdigest()


def test_chunk_leaf_parent_idx_in_range():
    c = _make_chunker(parent_size=10, parent_overlap=2, leaf_size=4, leaf_overlap=1)
    parents, leaves = c.chunk("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    parent_ids = {p.idx for p in parents}
    for leaf in leaves:
        assert leaf.parent_idx in parent_ids


def test_chunk_sentence_boundary_snap():
    """When a sentence ends inside the size budget, the chunk should stop there."""
    c = _make_chunker(parent_size=20, parent_overlap=2, leaf_size=10, leaf_overlap=2)
    # 'Hello.' = 6 codepoints; 'World.' = 6; together 12 chars + space = 13.
    parents, leaves = c.chunk("Hello. World. Bye.")
    # At least one parent should end exactly at a '.' character.
    assert any(p.text.rstrip().endswith(".") for p in parents)


def test_chunk_overlap_validation_constructor():
    with pytest.raises(ValueError):
        Chunker(parent_size=10, parent_overlap=10, leaf_size=4, leaf_overlap=1)
    with pytest.raises(ValueError):
        Chunker(parent_size=4, parent_overlap=1, leaf_size=4, leaf_overlap=1)
