from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Optional


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"\b(?:\+?82[- ]?)?0\d{1,2}[- ]?\d{3,4}[- ]?\d{4}\b")
_KOREAN_RRN_RE = re.compile(r"\b\d{6}[- ]?[1-4]\d{6}\b")
_POSIX_PATH_RE = re.compile(r"(?<!https:)(?<!http:)(?<!\w)/(?:data|mnt|home|Users|var|srv|opt)/[^\s]+")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s]+")
_PROJECT_CODE_RE = re.compile(r"\b(?:PROJECT|PROJ|EXP|INT|CONF)[-_ ]?[A-Z0-9]{2,}\b", re.I)
_ASSET_CODE_RE = re.compile(r"\b[A-Z]{2,8}-\d{2,8}\b")
_KOREAN_SECRET_RE = re.compile(r"(사내|비공개|기밀|내부문서|중앙문서함|계약조건|계약금|마일스톤)")


@dataclass
class DlpDecision:
    allowed: bool
    redacted_query: str
    query_hash: str
    blocked_reason: Optional[str] = None
    matched_signals: list[str] = field(default_factory=list)


def _extra_terms() -> list[str]:
    raw = os.getenv("M8_CONFIDENTIAL_TERMS", "")
    return [t.strip() for t in raw.split(",") if t.strip()]


def _hash_query(query: str) -> str:
    salt = os.getenv("M8_AUDIT_HASH_SALT", "m8-web-search")
    return hashlib.sha256(f"{salt}:{query}".encode("utf-8")).hexdigest()


def sanitize_query(query: str) -> DlpDecision:
    """Return a public-safe decision without exposing raw query in audit logs."""
    redacted = query
    signals: list[str] = []

    checks = [
        ("email", _EMAIL_RE),
        ("phone", _PHONE_RE),
        ("korean_rrn", _KOREAN_RRN_RE),
        ("posix_path", _POSIX_PATH_RE),
        ("windows_path", _WINDOWS_PATH_RE),
        ("project_code", _PROJECT_CODE_RE),
        ("asset_code", _ASSET_CODE_RE),
        ("korean_secret_term", _KOREAN_SECRET_RE),
    ]
    for name, pattern in checks:
        if pattern.search(redacted):
            signals.append(name)
            redacted = pattern.sub("[REDACTED]", redacted)

    for term in _extra_terms():
        if term.lower() in redacted.lower():
            signals.append("configured_secret_term")
            redacted = re.sub(re.escape(term), "[REDACTED]", redacted, flags=re.I)

    compact = re.sub(r"\s+", " ", redacted).strip()
    if signals:
        return DlpDecision(
            allowed=False,
            redacted_query=compact,
            query_hash=_hash_query(query),
            blocked_reason="query_contains_sensitive_data",
            matched_signals=signals,
        )

    if len(compact) < 2:
        return DlpDecision(
            allowed=False,
            redacted_query=compact,
            query_hash=_hash_query(query),
            blocked_reason="query_too_short_after_sanitization",
            matched_signals=["too_short"],
        )

    return DlpDecision(
        allowed=True,
        redacted_query=compact,
        query_hash=_hash_query(query),
        matched_signals=[],
    )
