from app.dlp import sanitize_query


def test_public_query_allowed():
    decision = sanitize_query("p53 phase 2 clinical trial")
    assert decision.allowed is True
    assert decision.redacted_query == "p53 phase 2 clinical trial"


def test_email_is_blocked():
    decision = sanitize_query("find papers for sae@example.com p53")
    assert decision.allowed is False
    assert "email" in decision.matched_signals
    assert "[REDACTED]" in decision.redacted_query


def test_internal_path_is_blocked():
    decision = sanitize_query("summarize /data/secret/protocol.pdf")
    assert decision.allowed is False
    assert "posix_path" in decision.matched_signals


def test_internal_project_code_is_blocked():
    decision = sanitize_query("PROJECT ALPHA EXP-123 toxicity data")
    assert decision.allowed is False
    assert "project_code" in decision.matched_signals or "asset_code" in decision.matched_signals
