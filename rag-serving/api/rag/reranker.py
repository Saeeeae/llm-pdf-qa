import logging
from shared.models.registry import registry

logger = logging.getLogger(__name__)


def _format_rerank_text(chunk: list[dict] | dict) -> str:
    block_type = chunk.get("block_type") or chunk.get("chunk_type") or "text"
    location_parts = []
    if chunk.get("page_number"):
        location_parts.append(f"page={chunk['page_number']}")
    if chunk.get("sheet_name"):
        location_parts.append(f"sheet={chunk['sheet_name']}")
    if chunk.get("slide_number"):
        location_parts.append(f"slide={chunk['slide_number']}")
    if chunk.get("section_path"):
        location_parts.append(f"section={chunk['section_path']}")

    header = f"[type={block_type}"
    if location_parts:
        header += " | " + " | ".join(location_parts)
    header += "]"
    return f"{header}\n{chunk['content'][:512]}"


def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    if not chunks:
        return []
    model = registry.reranker()
    pairs = [(query, _format_rerank_text(c)) for c in chunks]
    scores = model.predict(pairs)
    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = float(score)
    ranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
    return ranked[:top_k]
