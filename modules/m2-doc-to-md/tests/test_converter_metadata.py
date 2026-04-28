"""Frontmatter + page-marker normalization tests for m2 converter."""
from app.pipeline.converter import _normalize_page_markers


def test_no_markers_returns_zero_count():
    body = "Just a paragraph with no page markers anywhere."
    out, count = _normalize_page_markers(body)
    assert out == body
    assert count == 0


def test_html_comment_pattern_normalized():
    body = "<!-- page: 1 -->\nfoo\n<!-- page: 2 -->\nbar"
    out, count = _normalize_page_markers(body)
    assert "<!-- page: 1 -->" in out
    assert count == 2


def test_dashed_pattern_rewritten():
    body = "intro\n--- page 7 ---\nbody"
    out, count = _normalize_page_markers(body)
    assert "<!-- page: 7 -->" in out
    assert "--- page 7 ---" not in out
    assert count == 1


def test_bracket_pattern_rewritten():
    body = "[Page 3]\ntext"
    out, count = _normalize_page_markers(body)
    assert "<!-- page: 3 -->" in out
    assert count == 1


def test_form_feed_increments_counter():
    body = "page-one\n\f\npage-two\n\f\npage-three"
    out, count = _normalize_page_markers(body)
    # Form-feed has no captured number, so we synth from running counter.
    assert count == 2
    assert out.count("<!-- page:") == 2


def test_bare_page_n_only_when_alone_on_line():
    # 'Page 4' on its own line counts; inline mention does not.
    body = "Page 4\nsome body that mentions Page 99 in prose"
    out, count = _normalize_page_markers(body)
    assert "<!-- page: 4 -->" in out
    assert "Page 99" in out  # inline mention preserved
    assert count == 1
