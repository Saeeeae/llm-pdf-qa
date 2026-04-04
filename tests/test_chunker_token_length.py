import os
os.environ.setdefault("SMOKE_TEST_MODE", "true")

from rag_pipeline.pipeline.chunker import token_length


def test_korean_token_length_approximation():
    """Korean syllables should be ~1 token each, not len//4."""
    korean = "삼성전자가 올해 매출 목표를 상향 조정했습니다"
    result = token_length(korean)
    assert 12 <= result <= 30, f"Korean token count {result} is unreasonable"


def test_english_token_length_approximation():
    """English should remain roughly word-count * 1.3."""
    english = "Samsung Electronics has raised its revenue target for this year"
    result = token_length(english)
    assert 8 <= result <= 18, f"English token count {result} is unreasonable"


def test_mixed_token_length():
    """Mixed Korean/English text should combine both heuristics."""
    mixed = "삼성전자 Samsung의 2024년 revenue는 300조원입니다"
    result = token_length(mixed)
    assert 10 <= result <= 25, f"Mixed token count {result} is unreasonable"


def test_empty_and_whitespace():
    assert token_length("") == 0
    assert token_length("   ") == 0
