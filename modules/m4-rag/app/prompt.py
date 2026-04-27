from typing import List, Dict, Optional

SYS = (
    "You are a helpful assistant. "
    "Answer using only the provided context. "
    "Cite sources as [n]."
)


def build(
    query: str,
    sources: List[Dict],
    history: Optional[List[Dict]] = None,
    max_chars: int = 16000,
) -> List[Dict]:
    """Build chat messages list with context window guard."""
    ctx_parts: List[str] = []
    total = 0
    for i, s in enumerate(sources, 1):
        snip = f"[{i}] (doc:{s['doc_id']}#{s['chunk_idx']}) {s['text']}"
        if total + len(snip) > max_chars:
            break
        ctx_parts.append(snip)
        total += len(snip)

    ctx = "\n\n".join(ctx_parts)
    msgs: List[Dict] = [{"role": "system", "content": SYS}]
    if history:
        msgs.extend(history[-10:])
    msgs.append({"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {query}"})
    return msgs
