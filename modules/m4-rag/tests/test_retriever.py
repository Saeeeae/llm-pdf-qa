"""RRF fusion logic unit tests (no real DB needed)."""
import pytest


def _make_row(id_, doc_id, chunk_idx, text, score):
    return {"id": id_, "doc_id": doc_id, "chunk_idx": chunk_idx, "text": text, "metadata": {}, "score": score}


def _rrf_fuse(vec_rows, bm_rows, k=10):
    """Inline re-implementation of the fusion logic for isolated testing."""
    rrf = {}
    for rank, r in enumerate(vec_rows):
        entry = rrf.setdefault(r["id"], {**r, "rrf": 0.0})
        entry["rrf"] += 1 / (60 + rank)
    for rank, r in enumerate(bm_rows):
        entry = rrf.setdefault(r["id"], {**r, "rrf": 0.0})
        entry["rrf"] += 1 / (60 + rank)
    return sorted(rrf.values(), key=lambda x: x["rrf"], reverse=True)[:k]


def test_rrf_top_rank_wins():
    vec = [_make_row(1, "d1", 0, "alpha", 0.9), _make_row(2, "d2", 0, "beta", 0.7)]
    bm = [_make_row(1, "d1", 0, "alpha", 0.8), _make_row(3, "d3", 0, "gamma", 0.6)]
    result = _rrf_fuse(vec, bm)
    # id=1 appears in both lists → highest combined RRF score
    assert result[0]["id"] == 1


def test_rrf_only_in_one_list():
    vec = [_make_row(10, "d10", 0, "vec only", 0.95)]
    bm = [_make_row(20, "d20", 0, "bm only", 0.90)]
    result = _rrf_fuse(vec, bm)
    # Both get 1/60; id=10 ranked first in vec so equal score — order stable
    assert {r["id"] for r in result} == {10, 20}


def test_rrf_deduplication():
    row = _make_row(5, "d5", 2, "dup", 0.8)
    vec = [row]
    bm = [row]
    result = _rrf_fuse(vec, bm)
    ids = [r["id"] for r in result]
    assert ids.count(5) == 1


def test_rrf_truncates_to_k():
    vec = [_make_row(i, f"d{i}", 0, f"t{i}", 0.5) for i in range(20)]
    bm = []
    result = _rrf_fuse(vec, bm, k=5)
    assert len(result) == 5


def test_rrf_empty_inputs():
    assert _rrf_fuse([], []) == []


def test_rrf_scores_descending():
    vec = [_make_row(i, f"d{i}", 0, f"t{i}", 0.5) for i in range(5)]
    bm = [_make_row(i, f"d{i}", 0, f"t{i}", 0.5) for i in reversed(range(3))]
    result = _rrf_fuse(vec, bm)
    scores = [r["rrf"] for r in result]
    assert scores == sorted(scores, reverse=True)
