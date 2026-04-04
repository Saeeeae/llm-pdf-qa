import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("SMOKE_TEST_MODE", "true")

# Mock numpy before any import that depends on it (registry.py imports numpy)
if "numpy" not in sys.modules:
    sys.modules["numpy"] = MagicMock()

from rag_serving.api.rag.reranker import (
    _normalize_scores,
    _query_hints,
    _format_rerank_text,
    _compute_feature_score,
    rerank,
)


def _make_chunk(content="test content", **overrides):
    base = {
        "chunk_id": 1,
        "doc_id": 1,
        "content": content,
        "block_type": "text",
        "chunk_type": "text",
        "file_name": "report.pdf",
        "page_number": 1,
        "section_path": "",
        "sheet_name": "",
        "slide_number": "",
        "rrf_score": 0.5,
        "final_score": 0.5,
        "freshness_boost": 0.0,
        "multi_signal_boost": 0.0,
        "retrieval_intent": "general",
    }
    base.update(overrides)
    return base


def test_normalize_scores_empty():
    assert _normalize_scores([]) == []


def test_normalize_scores_identical():
    assert _normalize_scores([0.5, 0.5, 0.5]) == [0.5, 0.5, 0.5]


def test_normalize_scores_range():
    result = _normalize_scores([1.0, 2.0, 3.0])
    assert result[0] == 0.0
    assert result[-1] == 1.0


def test_query_hints_korean_table():
    hints = _query_hints("엑셀 표에서 매출 데이터를 보여줘")
    assert hints["table"] is True


def test_query_hints_recency():
    hints = _query_hints("최신 보고서 찾아줘")
    assert hints["recency"] is True


def test_query_hints_no_hints():
    hints = _query_hints("일반적인 질문입니다")
    assert not any(hints.values())


def test_format_rerank_text_includes_metadata():
    chunk = _make_chunk(page_number=3, file_name="report.pdf")
    text = _format_rerank_text(chunk)
    assert "page=3" in text
    assert "file=report.pdf" in text


def test_format_rerank_text_includes_content():
    chunk = _make_chunk(content="important data here")
    text = _format_rerank_text(chunk)
    assert "important data here" in text


def test_compute_feature_score_exact_match():
    chunk = _make_chunk(content="삼성전자 2024년 매출 보고서")
    hints = {"table": False, "image": False, "slide": False, "page": False, "recency": False}
    score = _compute_feature_score("삼성전자 매출", chunk, hints=hints, query_terms=["삼성전자", "매출"])
    assert score > 0.0


def test_compute_feature_score_table_intent():
    chunk = _make_chunk(content="data", block_type="table", retrieval_intent="table")
    hints = {"table": True, "image": False, "slide": False, "page": False, "recency": False}
    score = _compute_feature_score("표 보여줘", chunk, hints=hints, query_terms=["표"])
    assert score > 0.1  # Should get table block type boost


def test_rerank_returns_top_k():
    chunks = [_make_chunk(content=f"chunk {i}", chunk_id=i) for i in range(10)]
    result = rerank("test query", chunks, top_k=3)
    assert len(result) == 3


def test_rerank_empty():
    assert rerank("query", [], top_k=5) == []


def test_rerank_preserves_score_fields():
    chunks = [_make_chunk()]
    result = rerank("query", chunks, top_k=1)
    assert "rerank_score" in result[0]
    assert "rerank_model_score" in result[0]
    assert "rerank_feature_score" in result[0]
    assert "rerank_model_norm" in result[0]
    assert "rerank_prior_norm" in result[0]


def test_mmr_promotes_diversity():
    """Chunks from different docs should be promoted over same-doc clusters."""
    chunks = [
        _make_chunk(content="revenue Q1", doc_id=1, chunk_id=1, rrf_score=0.9, final_score=0.9),
        _make_chunk(content="revenue Q2", doc_id=1, chunk_id=2, rrf_score=0.88, final_score=0.88),
        _make_chunk(content="revenue Q3", doc_id=1, chunk_id=3, rrf_score=0.86, final_score=0.86),
        _make_chunk(content="competitor analysis", doc_id=2, chunk_id=4, rrf_score=0.85, final_score=0.85),
        _make_chunk(content="market overview", doc_id=3, chunk_id=5, rrf_score=0.80, final_score=0.80),
    ]
    result = rerank("revenue analysis", chunks, top_k=3)
    doc_ids = [c["doc_id"] for c in result]
    assert len(set(doc_ids)) >= 2, f"Expected diversity, got doc_ids={doc_ids}"


def test_classify_query_type_factoid():
    from rag_serving.api.rag.reranker import _classify_query_type
    assert _classify_query_type("CEO는 누구인가요?") == "factoid"
    assert _classify_query_type("What is the revenue?") == "factoid"


def test_classify_query_type_analytical():
    from rag_serving.api.rag.reranker import _classify_query_type
    assert _classify_query_type("시장 전망을 분석해줘") == "analytical"


def test_classify_query_type_comparison():
    from rag_serving.api.rag.reranker import _classify_query_type
    assert _classify_query_type("삼성과 LG를 비교해줘") == "comparison"


def test_classify_query_type_general():
    from rag_serving.api.rag.reranker import _classify_query_type
    assert _classify_query_type("안녕하세요") == "general"


def test_calibrate_scores_sigmoid():
    from rag_serving.api.rag.reranker import _calibrate_scores
    result = _calibrate_scores([0.0, 5.0, -5.0])
    assert 0.49 < result[0] < 0.51  # sigmoid(0) ≈ 0.5
    assert result[1] > 0.99         # sigmoid(5) ≈ 0.993
    assert result[2] < 0.01         # sigmoid(-5) ≈ 0.007


def test_calibrate_scores_empty():
    from rag_serving.api.rag.reranker import _calibrate_scores
    assert _calibrate_scores([]) == []
