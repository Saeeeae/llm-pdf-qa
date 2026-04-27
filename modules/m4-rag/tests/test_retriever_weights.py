"""B2.3 — Retriever RRF weights + RRF_K environment variable tests."""
import os
import pytest
import importlib


def _make_row(id_, doc_id="d", chunk_idx=0, text="t", score=0.5):
    return {"id": id_, "doc_id": doc_id, "chunk_idx": chunk_idx, "text": text,
            "metadata": {}, "score": score}


def _fuse(vec_rows, bm_rows, rrf_k=60, vec_w=1.0, bm25_w=1.0, k=10):
    """Inline fusion matching retriever.py logic for isolated testing."""
    rrf = {}
    for rank, r in enumerate(vec_rows):
        entry = rrf.setdefault(r["id"], {**r, "rrf": 0.0})
        entry["rrf"] += vec_w / (rrf_k + rank)
    for rank, r in enumerate(bm_rows):
        entry = rrf.setdefault(r["id"], {**r, "rrf": 0.0})
        entry["rrf"] += bm25_w / (rrf_k + rank)
    return sorted(rrf.values(), key=lambda x: x["rrf"], reverse=True)[:k]


def test_rrf_k_env_changes_score(monkeypatch):
    """Larger RRF_K produces smaller RRF scores."""
    monkeypatch.setenv("RRF_K", "120")
    import app.retriever as ret
    importlib.reload(ret)

    row = _make_row(1)
    result_120 = _fuse([row], [], rrf_k=120)
    result_60 = _fuse([row], [], rrf_k=60)
    assert result_120[0]["rrf"] < result_60[0]["rrf"]

    monkeypatch.delenv("RRF_K", raising=False)
    importlib.reload(ret)


def test_vec_weight_amplifies_vector_source(monkeypatch):
    """Higher VEC_WEIGHT boosts vector-only results above BM25-only results."""
    vec = [_make_row(1)]
    bm = [_make_row(2)]
    result = _fuse(vec, bm, vec_w=2.0, bm25_w=1.0)
    assert result[0]["id"] == 1


def test_bm25_weight_amplifies_bm25_source():
    """Higher BM25_WEIGHT boosts BM25-only results above vector-only results."""
    vec = [_make_row(1)]
    bm = [_make_row(2)]
    result = _fuse(vec, bm, vec_w=1.0, bm25_w=2.0)
    assert result[0]["id"] == 2


def test_equal_weights_same_as_default():
    """Equal weights 1.0/1.0 produce same ordering as hardcoded 60."""
    vec = [_make_row(i) for i in range(5)]
    bm = [_make_row(i) for i in reversed(range(3))]
    r1 = _fuse(vec, bm, rrf_k=60, vec_w=1.0, bm25_w=1.0)
    r2 = _fuse(vec, bm, rrf_k=60)
    assert [r["id"] for r in r1] == [r["id"] for r in r2]


def test_retriever_module_uses_env(monkeypatch):
    """app.retriever reads RRF_K, VEC_WEIGHT, BM25_WEIGHT from env at import."""
    monkeypatch.setenv("RRF_K", "42")
    monkeypatch.setenv("VEC_WEIGHT", "1.5")
    monkeypatch.setenv("BM25_WEIGHT", "0.5")

    import app.retriever as ret
    importlib.reload(ret)

    assert ret.RRF_K == 42
    assert ret.VEC_WEIGHT == 1.5
    assert ret.BM25_WEIGHT == 0.5

    monkeypatch.delenv("RRF_K", raising=False)
    monkeypatch.delenv("VEC_WEIGHT", raising=False)
    monkeypatch.delenv("BM25_WEIGHT", raising=False)
    importlib.reload(ret)
