"""Reranker score-fusion and MMR diversification tests.

The actual cross-encoder is monkey-patched so the suite stays offline.
"""
from app.reranker import normalize


def test_normalize_basic():
    assert normalize([]) == []
    assert normalize([1.0, 2.0, 3.0]) == [0.0, 0.5, 1.0]


def test_normalize_constant_inputs():
    # All equal → 0.5 by convention
    assert normalize([4.2, 4.2, 4.2]) == [0.5, 0.5, 0.5]


# ─── rerank() with a stubbed cross-encoder ─────────────────────────────────
def test_rerank_changes_ranking(monkeypatch):
    """If CE strongly prefers the second candidate, it should rank first."""
    from app import retriever as r
    from app import reranker as rk

    class FakeCE:
        @classmethod
        def get(cls):
            inst = cls()
            return inst

        def score(self, query, texts, batch_size=32):
            # Last text gets the highest CE score
            return [0.1] * (len(texts) - 1) + [0.9]

    monkeypatch.setattr(rk, "Reranker", FakeCE)
    monkeypatch.setattr(r, "USE_RERANKER", True)
    monkeypatch.setattr(r, "RERANK_ALPHA", 1.0)  # CE only

    cands = [
        {"id": 1, "text": "alpha", "rrf": 0.5, "embedding": "[1.0,0.0]"},
        {"id": 2, "text": "beta",  "rrf": 0.4, "embedding": "[0.0,1.0]"},
        {"id": 3, "text": "gamma", "rrf": 0.3, "embedding": "[1.0,1.0]"},
    ]
    out = r.rerank("q", cands, alpha=1.0)
    assert out[0]["id"] == 3  # CE-favored gamma promoted to top


def test_rerank_disabled_passthrough(monkeypatch):
    from app import retriever as r
    monkeypatch.setattr(r, "USE_RERANKER", False)

    cands = [
        {"id": 1, "text": "a", "rrf": 0.9, "embedding": "[1.0,0.0]"},
        {"id": 2, "text": "b", "rrf": 0.5, "embedding": "[0.0,1.0]"},
    ]
    out = r.rerank("q", cands)
    assert [c["id"] for c in out] == [1, 2]
    assert out[0]["final"] == out[0]["rrf"]
    assert out[0]["ce"] is None


def test_rerank_handles_empty_input(monkeypatch):
    from app import retriever as r
    assert r.rerank("q", []) == []


# ─── MMR ────────────────────────────────────────────────────────────────────
def test_mmr_pure_relevance_preserves_order():
    """λ=1 is "relevance only" — must not re-order by diversity."""
    from app.retriever import mmr_diversify
    cands = [
        {"id": 1, "final": 0.9, "embedding": "[1,0]"},
        {"id": 2, "final": 0.8, "embedding": "[0,1]"},
        {"id": 3, "final": 0.7, "embedding": "[1,0]"},  # duplicate of id=1
    ]
    out = mmr_diversify(cands, k=3, lambda_=1.0)
    assert [c["id"] for c in out] == [1, 2, 3]


def test_mmr_diversity_demotes_duplicate():
    """λ=0 is "diversity only" — duplicate-of-best should be pushed last."""
    from app.retriever import mmr_diversify
    cands = [
        {"id": 1, "final": 0.9, "embedding": "[1,0]"},
        {"id": 2, "final": 0.85, "embedding": "[1,0]"},  # near-dup of #1
        {"id": 3, "final": 0.5, "embedding": "[0,1]"},   # orthogonal
    ]
    out = mmr_diversify(cands, k=3, lambda_=0.0)
    assert out[0]["id"] == 1
    assert out[1]["id"] == 3   # orthogonal picked over the duplicate
    assert out[2]["id"] == 2


def test_mmr_truncates_to_k():
    from app.retriever import mmr_diversify
    cands = [
        {"id": i, "final": 1.0 - 0.01 * i, "embedding": f"[{i},0]"} for i in range(20)
    ]
    out = mmr_diversify(cands, k=5)
    assert len(out) == 5


def test_mmr_empty():
    from app.retriever import mmr_diversify
    assert mmr_diversify([], k=5) == []


# ─── hybrid_search MMR-skip path ───────────────────────────────────────────
def test_hybrid_search_skips_mmr_when_lambda_one(monkeypatch):
    """MMR_LAMBDA >= 0.999 disables MMR + the embedding fetch in retrieve()."""
    import asyncio
    from unittest.mock import AsyncMock
    from app import retriever as r

    monkeypatch.setattr(r, "MMR_LAMBDA", 1.0)
    monkeypatch.setattr(r, "USE_RERANKER", False)

    captured = {}

    async def fake_retrieve(db, query, embedding, k, folder_filter=None, need_embedding=True):
        captured["need_embedding"] = need_embedding
        return [
            {"id": 1, "doc_id": "d", "chunk_idx": 0, "text": "t",
             "metadata": {}, "parent_id": None, "folder_path": None,
             "embedding": None, "rrf": 0.5, "score": 0.5},
        ]

    async def fake_expand(db, leaves):
        return [dict(l, text=l["text"], leaf_text=l["text"], leaf_ids=[l["id"]],
                     score=l.get("rrf", 0.0)) for l in leaves]

    monkeypatch.setattr(r, "retrieve", fake_retrieve)
    monkeypatch.setattr(r, "expand_to_parents", fake_expand)
    # Stub out mmr_diversify to verify it is NOT called.
    mmr_called = AsyncMock()
    monkeypatch.setattr(r, "mmr_diversify", lambda *a, **k: (mmr_called(), [])[1])

    result = asyncio.run(r.hybrid_search(None, "q", [0.1] * 4, k=5))
    assert captured["need_embedding"] is False
    assert mmr_called.call_count == 0
    assert len(result) == 1


def test_hybrid_search_uses_mmr_by_default(monkeypatch):
    import asyncio
    from app import retriever as r

    monkeypatch.setattr(r, "MMR_LAMBDA", 0.5)
    monkeypatch.setattr(r, "USE_RERANKER", False)

    captured = {}

    async def fake_retrieve(db, query, embedding, k, folder_filter=None, need_embedding=True):
        captured["need_embedding"] = need_embedding
        return [
            {"id": 1, "doc_id": "d", "chunk_idx": 0, "text": "t",
             "metadata": {}, "parent_id": None, "folder_path": None,
             "embedding": "[1,0]", "rrf": 0.5, "score": 0.5},
        ]

    async def fake_expand(db, leaves):
        return list(leaves)

    monkeypatch.setattr(r, "retrieve", fake_retrieve)
    monkeypatch.setattr(r, "expand_to_parents", fake_expand)

    asyncio.run(r.hybrid_search(None, "q", [0.1] * 4, k=5))
    assert captured["need_embedding"] is True
