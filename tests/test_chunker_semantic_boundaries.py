import os
os.environ.setdefault("SMOKE_TEST_MODE", "true")

from rag_pipeline.pipeline.chunker import _split_by_tokens


def test_split_by_tokens_fallback_produces_chunks():
    """Word-based fallback should still split long text into multiple chunks."""
    # Generate enough words to exceed chunk_size (word count in fallback mode)
    words = [f"word{i}" for i in range(50)]
    text = " ".join(words)
    chunks = _split_by_tokens(text, chunk_size=10, chunk_overlap=2)
    assert len(chunks) >= 3, f"Expected multiple chunks, got {len(chunks)}"


def test_split_by_tokens_fallback_handles_korean():
    """Korean text should be split by the fallback splitter without errors."""
    text = " ".join([f"한국어문장{i}" for i in range(30)])
    chunks = _split_by_tokens(text, chunk_size=8, chunk_overlap=2)
    assert len(chunks) >= 2


def test_korean_separators_in_source():
    """Verify Korean sentence endings are defined in the separators list."""
    import inspect
    source = inspect.getsource(_split_by_tokens)
    # These Korean endings should be in the separators list
    assert "습니다. " in source
    assert "됩니다. " in source
    assert "입니다. " in source
    assert "했다. " in source
    assert "다. " in source
    assert "요. " in source
