"""Prompt builder tests — context window guard and message structure."""
import pytest
from app.prompt import build, SYS


def _src(i, text="x" * 100):
    return {"doc_id": f"doc{i}", "chunk_idx": i, "text": text}


def test_system_message_first():
    msgs = build("q", [_src(1)])
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == SYS


def test_user_message_last():
    msgs = build("hello", [_src(1)])
    assert msgs[-1]["role"] == "user"
    assert "hello" in msgs[-1]["content"]


def test_context_included():
    src = _src(1, "unique_text_abc")
    msgs = build("q", [src])
    assert "unique_text_abc" in msgs[-1]["content"]


def test_citation_format():
    src = _src(3, "some text")
    msgs = build("q", [src])
    user_content = msgs[-1]["content"]
    assert "[1] (doc:doc3#3)" in user_content


def test_max_chars_truncates():
    # Each source ~110 chars; limit to 200 → only first fits
    sources = [_src(i, "x" * 100) for i in range(5)]
    msgs = build("q", sources, max_chars=200)
    user_content = msgs[-1]["content"]
    # Only [1] should appear, not [3] or beyond
    assert "[1]" in user_content
    assert "[3]" not in user_content


def test_history_appended():
    history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ans"}]
    msgs = build("q", [_src(1)], history=history)
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user"]


def test_history_capped_at_10():
    history = [{"role": "user", "content": str(i)} for i in range(20)]
    msgs = build("q", [_src(1)], history=history)
    # system + last 10 history + user query = 12
    assert len(msgs) == 12


def test_empty_sources():
    msgs = build("q", [])
    assert msgs[-1]["role"] == "user"
    assert "Question: q" in msgs[-1]["content"]
