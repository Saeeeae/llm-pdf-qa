import logging

from rag_serving.config import serving_settings
from shared.models.registry import registry
from shared.search_terms import extract_candidate_terms, normalize_search_text

logger = logging.getLogger(__name__)

TABLE_HINTS = {"table", "표", "sheet", "excel", "엑셀", "row", "column", "행", "열", "셀"}
IMAGE_HINTS = {"image", "figure", "fig", "chart", "diagram", "사진", "이미지", "그림", "도표", "차트"}
SLIDE_HINTS = {"slide", "slides", "슬라이드", "deck", "ppt", "pptx"}
PAGE_HINTS = {"page", "pages", "페이지"}
RECENCY_HINTS = {"latest", "recent", "newest", "updated", "최신", "최근", "요즘", "업데이트", "신규"}


def _query_hints(query: str) -> dict[str, bool]:
    normalized = normalize_search_text(query)
    return {
        "table": any(term in normalized for term in TABLE_HINTS),
        "image": any(term in normalized for term in IMAGE_HINTS),
        "slide": any(term in normalized for term in SLIDE_HINTS),
        "page": any(term in normalized for term in PAGE_HINTS),
        "recency": any(term in normalized for term in RECENCY_HINTS),
    }


def _normalize_block_type(chunk: dict) -> str:
    return normalize_search_text(chunk.get("block_type") or chunk.get("chunk_type") or "text") or "text"


def _normalize_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if maximum - minimum < 1e-9:
        return [0.5 for _ in values]
    return [(value - minimum) / (maximum - minimum) for value in values]


def _format_rerank_text(chunk: dict) -> str:
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
    if chunk.get("file_name"):
        location_parts.append(f"file={chunk['file_name']}")

    header = f"[type={block_type}"
    if location_parts:
        header += " | " + " | ".join(location_parts)
    header += "]"
    return f"{header}\n{chunk['content'][:512]}"


def _compute_feature_score(query: str, chunk: dict, *, hints: dict[str, bool], query_terms: list[str]) -> float:
    normalized_query = normalize_search_text(query)
    block_type = _normalize_block_type(chunk)
    intent = str(chunk.get("retrieval_intent") or "general")
    file_name = str(chunk.get("file_name") or "")
    content = str(chunk.get("content") or "")
    section_path = str(chunk.get("section_path") or "")
    sheet_name = str(chunk.get("sheet_name") or "")
    slide_number = str(chunk.get("slide_number") or "")
    page_number = str(chunk.get("page_number") or "")

    haystack = normalize_search_text(
        " ".join(
            part
            for part in [
                file_name,
                content,
                section_path,
                sheet_name,
                slide_number,
                page_number,
                block_type,
            ]
            if part
        )
    )

    score = 0.0

    if normalized_query and normalized_query in haystack:
        score += 0.12

    term_hits = sum(1 for term in query_terms if term and term in haystack)
    if query_terms:
        score += min((term_hits / len(query_terms)) * 0.18, 0.18)

    file_name_norm = normalize_search_text(file_name)
    section_norm = normalize_search_text(section_path)
    if file_name_norm and any(term in file_name_norm for term in query_terms):
        score += 0.05
    if section_norm and any(term in section_norm for term in query_terms):
        score += 0.04

    if intent == "table":
        if block_type == "table":
            score += 0.18
        elif block_type == "caption":
            score += 0.08
    elif intent == "image":
        if block_type == "image":
            score += 0.18
        elif block_type == "caption":
            score += 0.1
    elif intent == "caption" and block_type == "caption":
        score += 0.18
    elif intent == "slide":
        if chunk.get("slide_number"):
            score += 0.12
        if block_type == "caption":
            score += 0.04
    elif intent == "page" and chunk.get("page_number"):
        score += 0.12

    if hints["table"] and block_type == "table" and "|" in content:
        score += 0.08
    if hints["image"] and block_type in {"image", "caption"}:
        score += 0.07
    if hints["slide"] and chunk.get("slide_number"):
        score += 0.06
    if hints["page"] and chunk.get("page_number"):
        score += 0.05
    if sheet_name and hints["table"]:
        score += 0.04

    if hints["recency"]:
        score += min(float(chunk.get("freshness_boost") or 0.0) * 2.5, 0.18)
    else:
        score += min(float(chunk.get("freshness_boost") or 0.0), 0.04)

    score += min(float(chunk.get("multi_signal_boost") or 0.0) * 2.0, 0.08)
    return round(min(score, 1.0), 4)


def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    if not chunks:
        return []

    model = registry.reranker()
    pairs = [(query, _format_rerank_text(c)) for c in chunks]
    model_scores = [float(score) for score in model.predict(pairs)]
    model_norm_scores = _normalize_scores(model_scores)
    prior_scores = [float(chunk.get("final_score") or chunk.get("rrf_score") or 0.0) for chunk in chunks]
    prior_norm_scores = _normalize_scores(prior_scores)
    hints = _query_hints(query)
    query_terms = [
        normalize_search_text(term)
        for term in [query, *extract_candidate_terms(query)]
        if normalize_search_text(term)
    ]
    query_terms = list(dict.fromkeys(query_terms))

    for chunk, model_score, model_norm, prior_norm in zip(
        chunks,
        model_scores,
        model_norm_scores,
        prior_norm_scores,
    ):
        feature_score = _compute_feature_score(query, chunk, hints=hints, query_terms=query_terms)
        combined_score = (
            model_norm * serving_settings.rerank_model_weight
            + prior_norm * serving_settings.rerank_prior_weight
            + feature_score * serving_settings.rerank_feature_weight
        )
        chunk["rerank_model_score"] = round(model_score, 4)
        chunk["rerank_model_norm"] = round(model_norm, 4)
        chunk["rerank_prior_norm"] = round(prior_norm, 4)
        chunk["rerank_feature_score"] = feature_score
        chunk["rerank_score"] = round(combined_score, 4)

    ranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
    return ranked[:top_k]
