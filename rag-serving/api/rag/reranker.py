import logging
import math

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


def _calibrate_scores(values: list[float]) -> list[float]:
    """Sigmoid calibration for stable [0,1] score distribution."""
    if not values:
        return []
    return [1.0 / (1.0 + math.exp(-v)) for v in values]


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


def _apply_mmr(chunks: list[dict], top_k: int, mmr_lambda: float) -> list[dict]:
    """Greedy MMR selection using metadata-based diversity penalty."""
    if not chunks or mmr_lambda >= 1.0:
        return chunks[:top_k]

    selected: list[dict] = []
    remaining = list(chunks)

    selected.append(remaining.pop(0))

    while len(selected) < top_k and remaining:
        best_idx = 0
        best_mmr = -float("inf")

        selected_doc_ids = {c["doc_id"] for c in selected}
        selected_sections = {c.get("section_path") or "" for c in selected}

        for i, candidate in enumerate(remaining):
            relevance = candidate["rerank_score"]
            penalty = 0.0
            if candidate["doc_id"] in selected_doc_ids:
                penalty += 0.3
            if (candidate.get("section_path") or "") in selected_sections and candidate.get("section_path"):
                penalty += 0.15
            mmr_score = mmr_lambda * relevance - (1 - mmr_lambda) * penalty
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i

        selected.append(remaining.pop(best_idx))

    return selected


_FACTOID_KW = {"누구", "무엇", "언제", "어디", "몇", "what", "who", "when", "where", "how many", "how much"}
_ANALYTICAL_KW = {"분석", "전망", "이유", "원인", "영향", "추세", "analyze", "why", "impact", "trend", "forecast"}
_COMPARISON_KW = {"비교", "차이", "대비", "versus", "compare", "vs", "difference", "대조"}


def _classify_query_type(query: str) -> str:
    normalized = normalize_search_text(query)
    if any(kw in normalized for kw in _COMPARISON_KW):
        return "comparison"
    if any(kw in normalized for kw in _ANALYTICAL_KW):
        return "analytical"
    if any(kw in normalized for kw in _FACTOID_KW):
        return "factoid"
    return "general"


def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    if not chunks:
        return []

    model = registry.reranker()
    pairs = [(query, _format_rerank_text(c)) for c in chunks]
    model_scores = [float(score) for score in model.predict(pairs)]
    model_norm_scores = _calibrate_scores(model_scores)
    prior_scores = [float(chunk.get("final_score") or chunk.get("rrf_score") or 0.0) for chunk in chunks]
    prior_norm_scores = _normalize_scores(prior_scores)
    hints = _query_hints(query)
    query_terms = [
        normalize_search_text(term)
        for term in [query, *extract_candidate_terms(query)]
        if normalize_search_text(term)
    ]
    query_terms = list(dict.fromkeys(query_terms))

    query_type = _classify_query_type(query)
    weight_map = {
        "factoid": serving_settings.rerank_weights_factoid,
        "analytical": serving_settings.rerank_weights_analytical,
        "comparison": serving_settings.rerank_weights_comparison,
    }
    if query_type in weight_map:
        parts = weight_map[query_type].split(",")
        w_model, w_prior, w_feature = float(parts[0]), float(parts[1]), float(parts[2])
    else:
        w_model = serving_settings.rerank_model_weight
        w_prior = serving_settings.rerank_prior_weight
        w_feature = serving_settings.rerank_feature_weight

    for chunk, model_score, model_norm, prior_norm in zip(
        chunks,
        model_scores,
        model_norm_scores,
        prior_norm_scores,
    ):
        feature_score = _compute_feature_score(query, chunk, hints=hints, query_terms=query_terms)
        combined_score = (
            model_norm * w_model
            + prior_norm * w_prior
            + feature_score * w_feature
        )
        chunk["rerank_model_score"] = round(model_score, 4)
        chunk["rerank_model_norm"] = round(model_norm, 4)
        chunk["rerank_prior_norm"] = round(prior_norm, 4)
        chunk["rerank_feature_score"] = feature_score
        chunk["rerank_score"] = round(combined_score, 4)

    ranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
    if serving_settings.rerank_mmr_enabled:
        return _apply_mmr(ranked, top_k, serving_settings.rerank_mmr_lambda)
    return ranked[:top_k]
