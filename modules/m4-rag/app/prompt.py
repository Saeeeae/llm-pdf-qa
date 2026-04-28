"""Prompt assembly for m4-rag.

Token-budget aware (approximate): bounds context + history by character budget
that maps to MAX_CONTEXT_TOKENS via CHARS_PER_TOKEN. CJK input compresses to
fewer tokens per character than Latin text, so we err on the conservative side
(default 2 chars/token).
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

# In-context truncation
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "6000"))
CHARS_PER_TOKEN = float(os.getenv("CHARS_PER_TOKEN", "2.0"))
HISTORY_TOKEN_BUDGET = int(os.getenv("HISTORY_TOKEN_BUDGET", "1500"))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "10"))

# When sources is empty, we tell the LLM to refuse to answer.
SYS_REAL = (
    "당신은 사내 문서 RAG 도우미입니다. 반드시 한국어로 답변하세요.\n"
    "규칙:\n"
    "1) 제공된 Context 안의 정보만 사용해 답하세요. 추측하지 마세요.\n"
    "2) 답변 근거를 제시할 때는 [n] 형식으로 인용하세요. n은 Context의 [n]과 일치해야 합니다.\n"
    "3) Context에 답이 없거나 충분하지 않으면 '제공된 문서에서 답을 찾을 수 없습니다.'라고 답하세요.\n"
    "4) 문서를 인용 없이 사실 주장처럼 쓰지 마세요."
)

SYS_REFUSE = (
    "당신은 사내 문서 RAG 도우미입니다. 반드시 한국어로 답변하세요.\n"
    "관련 문서를 찾지 못했다는 사실을 정중히 알리고, 사용자가 질의를 더 구체화하거나 "
    "다른 키워드로 시도하도록 안내하세요. 추측하지 마세요."
)


def _tokens_estimate(s: str) -> int:
    return int(len(s) / CHARS_PER_TOKEN) + 1


def trim_history(
    history: Optional[List[Dict]], budget_tokens: int = HISTORY_TOKEN_BUDGET,
) -> List[Dict]:
    """Keep most-recent turns within token budget. Drops oldest first."""
    if not history:
        return []
    kept: List[Dict] = []
    used = 0
    for msg in reversed(history[-MAX_HISTORY_TURNS:]):
        cost = _tokens_estimate(msg.get("content", ""))
        if used + cost > budget_tokens and kept:
            break
        kept.append(msg)
        used += cost
    return list(reversed(kept))


def format_source(idx: int, src: Dict) -> str:
    """Render one source block with citation tag and L1 metadata header."""
    folder = src.get("folder_path") or "?"
    doc_id = src.get("doc_id", "?")
    chunk_idx = src.get("chunk_idx", "?")
    md = src.get("metadata") or {}
    filename = md.get("filename") if isinstance(md, dict) else None
    head = f"[{idx}] doc={doc_id} chunk={chunk_idx}"
    if filename:
        head += f" file={filename}"
    if folder and folder != "?":
        head += f" folder={folder}"
    return f"{head}\n{src['text']}"


def build(
    query: str,
    sources: List[Dict],
    history: Optional[List[Dict]] = None,
) -> Tuple[List[Dict], int]:
    """Build chat messages and return (messages, kept_source_count).

    The kept_source_count tells the caller how many `[n]` citations are valid,
    so the response post-processor can drop hallucinated citations.
    """
    if not sources:
        msgs: List[Dict] = [{"role": "system", "content": SYS_REFUSE}]
        msgs.extend(trim_history(history))
        msgs.append({"role": "user", "content": query})
        return msgs, 0

    # Context budget is MAX_CONTEXT_TOKENS minus a small headroom for the
    # system prompt + question. We track it in characters.
    char_budget = int((MAX_CONTEXT_TOKENS - 600) * CHARS_PER_TOKEN)

    parts: List[str] = []
    used = 0
    kept = 0
    for i, s in enumerate(sources, 1):
        block = format_source(i, s)
        if used + len(block) > char_budget and parts:
            break
        parts.append(block)
        used += len(block) + 2
        kept += 1

    ctx = "\n\n".join(parts)
    msgs: List[Dict] = [{"role": "system", "content": SYS_REAL}]
    msgs.extend(trim_history(history))
    msgs.append(
        {"role": "user", "content": f"Context:\n{ctx}\n\n질문: {query}"}
    )
    return msgs, kept


# ─── Citation post-processing ──────────────────────────────────────────────
_CITE_RE = re.compile(r"\[(\d+)\]")


def validate_citations(answer: str, max_valid: int) -> Tuple[str, List[int]]:
    """Strip citations whose number is out of range. Return (cleaned, dropped).

    A citation `[n]` is valid iff 1 <= n <= max_valid. Out-of-range citations
    are removed silently — they signal hallucination by the LLM.
    """
    dropped: List[int] = []

    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        if 1 <= n <= max_valid:
            return m.group(0)
        dropped.append(n)
        return ""

    cleaned = _CITE_RE.sub(repl, answer)
    return cleaned, dropped
