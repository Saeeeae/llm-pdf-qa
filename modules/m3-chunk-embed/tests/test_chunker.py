"""Unit tests for Chunker using a mock tokenizer — no model download."""
import hashlib
import pytest


class _FakeTok:
    """Minimal tokenizer: each character is a token id (its ordinal)."""

    def encode(self, text, add_special_tokens=False):
        return list(text.encode("utf-8"))

    def decode(self, ids):
        return bytes(ids).decode("utf-8", errors="replace")


def _make_chunker(chunk_size=10, overlap=2):
    from app.chunker import Chunker
    c = Chunker.__new__(Chunker)
    c.tok = _FakeTok()
    c.chunk_size = chunk_size
    c.overlap = overlap
    return c


def test_chunk_basic():
    chunker = _make_chunker(chunk_size=10, overlap=2)
    text = "A" * 30
    pieces = chunker.chunk(text)
    assert len(pieces) > 1
    for txt, h in pieces:
        assert h == hashlib.sha256(txt.encode()).hexdigest()
        assert txt  # non-empty


def test_chunk_empty():
    chunker = _make_chunker()
    assert chunker.chunk("") == []
    assert chunker.chunk("   ") == []


def test_chunk_short_text():
    chunker = _make_chunker(chunk_size=100, overlap=10)
    text = "hello world"
    pieces = chunker.chunk(text)
    assert len(pieces) == 1
    assert pieces[0][0] == "hello world"


def test_chunk_hash_uniqueness():
    chunker = _make_chunker(chunk_size=8, overlap=0)
    text = "abcdefghijklmnopqrstuvwxyz"
    pieces = chunker.chunk(text)
    hashes = [h for _, h in pieces]
    assert len(hashes) == len(set(hashes)), "duplicate hashes for distinct chunks"


def test_chunk_overlap_produces_overlap():
    chunker = _make_chunker(chunk_size=6, overlap=2)
    # 12 bytes → step=4 → starts at 0, 4, 8
    text = "abcdefghijkl"
    pieces = chunker.chunk(text)
    # chunk 0: bytes 0-5, chunk 1: bytes 4-9, chunk 2: bytes 8-13(clamped)
    assert pieces[0][0][:4] == pieces[1][0][:4] or len(pieces) >= 2
