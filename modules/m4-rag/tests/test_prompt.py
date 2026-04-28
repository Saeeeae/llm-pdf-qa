"""Prompt builder + citation validator tests."""
from app.prompt import (
    SYS_REAL,
    SYS_REFUSE,
    build,
    trim_history,
    validate_citations,
)


def _src(i, text="x" * 100, folder=None, filename=None):
    md = {}
    if filename:
        md["filename"] = filename
    return {
        "doc_id": f"doc{i}",
        "chunk_idx": i,
        "text": text,
        "folder_path": folder,
        "metadata": md,
    }


def test_real_path_system_prompt():
    msgs, kept = build("q", [_src(1)])
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == SYS_REAL
    assert kept >= 1


def test_refuse_path_when_no_sources():
    msgs, kept = build("q", [])
    assert msgs[0]["content"] == SYS_REFUSE
    assert kept == 0
    # No "Context:" prefix in refusal path
    assert "Context" not in msgs[-1]["content"]


def test_user_message_has_question_in_korean_label():
    msgs, _ = build("hello", [_src(1)])
    assert msgs[-1]["role"] == "user"
    assert "질문: hello" in msgs[-1]["content"]


def test_citation_tag_format():
    msgs, _ = build("q", [_src(3, "some text", folder="reg/FDA", filename="a.pdf")])
    user_content = msgs[-1]["content"]
    assert "[1]" in user_content
    # L1 metadata leaks into the source header so the LLM can cite path/file.
    assert "doc=doc3" in user_content
    assert "file=a.pdf" in user_content
    assert "folder=reg/FDA" in user_content


def test_kept_count_matches_truncation(monkeypatch):
    # Force a tight char budget so only a subset of sources survives.
    monkeypatch.setenv("MAX_CONTEXT_TOKENS", "700")  # tight after 600-headroom subtraction
    monkeypatch.setenv("CHARS_PER_TOKEN", "2.0")
    import importlib
    import app.prompt as prompt_mod
    importlib.reload(prompt_mod)

    sources = [_src(i, "x" * 1000) for i in range(5)]
    msgs, kept = prompt_mod.build("q", sources)
    assert 1 <= kept < 5


def test_history_trim_drops_oldest_when_budget_tight():
    history = [
        {"role": "user", "content": "old " * 1000},
        {"role": "assistant", "content": "ans " * 1000},
        {"role": "user", "content": "recent"},
    ]
    kept = trim_history(history, budget_tokens=50)
    assert kept[-1]["content"] == "recent"
    assert len(kept) < 3


def test_validate_citations_keeps_in_range():
    cleaned, dropped = validate_citations("This [1] is fine [2] too.", max_valid=3)
    assert "[1]" in cleaned and "[2]" in cleaned
    assert dropped == []


def test_validate_citations_drops_out_of_range():
    cleaned, dropped = validate_citations("Real [1] hallucinated [9] mid", max_valid=3)
    assert "[1]" in cleaned
    assert "[9]" not in cleaned
    assert dropped == [9]


def test_validate_citations_empty_sources_strips_all():
    cleaned, dropped = validate_citations("[1] [2] [3]", max_valid=0)
    assert cleaned.strip() == ""
    assert sorted(dropped) == [1, 2, 3]
