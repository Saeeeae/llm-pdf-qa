import logging
from datetime import datetime, timezone

from sqlalchemy import bindparam, text
from rag_serving.config import serving_settings
from shared.db import get_session
from shared.search_terms import extract_candidate_terms, expand_terms, get_alias_rows, normalize_search_text

logger = logging.getLogger(__name__)

TABLE_HINTS = {"table", "표", "sheet", "excel", "엑셀", "row", "column", "행", "열", "셀"}
IMAGE_HINTS = {"image", "figure", "fig", "chart", "diagram", "사진", "이미지", "그림", "도표", "차트"}
CAPTION_HINTS = {"caption", "캡션", "figure legend", "table legend", "legend"}
SLIDE_HINTS = {"slide", "slides", "슬라이드", "deck", "ppt", "pptx"}
PAGE_HINTS = {"page", "pages", "페이지"}
RECENCY_HINTS = {"latest", "recent", "newest", "updated", "최신", "최근", "요즘", "업데이트", "신규"}


def _result_select(score_expression: str, score_alias: str) -> str:
    return f"""
        SELECT dc.chunk_id, dc.doc_id, dc.block_id, dc.chunk_idx, dc.content,
               COALESCE(blk.block_type, dc.chunk_type) AS block_type,
               dc.chunk_type, COALESCE(blk.page_number, dc.page_number) AS page_number,
               blk.sheet_name, blk.slide_number, blk.section_path,
               {score_expression} AS {score_alias},
               d.file_name, d.type AS file_type, d.updated_at
    """


def _detect_query_hints(normalized: str) -> dict[str, bool]:
    return {
        "table": any(term in normalized for term in TABLE_HINTS),
        "image": any(term in normalized for term in IMAGE_HINTS),
        "caption": any(term in normalized for term in CAPTION_HINTS),
        "slide": any(term in normalized for term in SLIDE_HINTS),
        "page": any(term in normalized for term in PAGE_HINTS),
        "recency": any(term in normalized for term in RECENCY_HINTS),
    }


def infer_block_type_preferences(query_text: str, expanded_terms: list[str]) -> dict[str, float]:
    normalized = normalize_search_text(" ".join([query_text, *expanded_terms]))
    hints = _detect_query_hints(normalized)
    preferences = {"text": 0.0, "table": 0.0, "image": 0.0, "caption": 0.0}

    if hints["table"]:
        preferences["table"] = 0.28
        preferences["caption"] = max(preferences["caption"], 0.08)
    if hints["image"]:
        preferences["image"] = 0.24
        preferences["caption"] = max(preferences["caption"], 0.16)
    if hints["caption"]:
        preferences["caption"] = max(preferences["caption"], 0.24)
    if hints["slide"]:
        preferences["text"] = max(preferences["text"], 0.06)
        preferences["caption"] = max(preferences["caption"], 0.1)
    if hints["page"]:
        preferences["text"] = max(preferences["text"], 0.04)

    return preferences


def classify_query_intent(query_text: str, expanded_terms: list[str]) -> dict[str, object]:
    normalized = normalize_search_text(" ".join([query_text, *expanded_terms]))
    hints = _detect_query_hints(normalized)
    preferences = infer_block_type_preferences(query_text, expanded_terms)

    primary_intent = "general"
    if hints["table"]:
        primary_intent = "table"
    elif hints["image"]:
        primary_intent = "image"
    elif hints["caption"]:
        primary_intent = "caption"
    elif hints["slide"]:
        primary_intent = "slide"
    elif hints["page"]:
        primary_intent = "page"

    budgets_by_intent = serving_settings.retrieval_budgets

    candidate_multiplier = serving_settings.retrieval_base_candidate_multiplier
    if primary_intent in {"table", "image", "caption", "slide"}:
        candidate_multiplier = serving_settings.retrieval_intent_candidate_multiplier
    if hints["recency"]:
        candidate_multiplier = max(candidate_multiplier, serving_settings.retrieval_intent_candidate_multiplier)

    return {
        "primary": primary_intent,
        "hints": hints,
        "preferences": preferences,
        "budgets": budgets_by_intent.get(primary_intent, {}),
        "candidate_multiplier": candidate_multiplier,
    }


def _normalize_block_type_name(block_type: str) -> str:
    return normalize_search_text(block_type) or block_type


def _normalize_block_types(block_types: list[str] | None) -> list[str]:
    if not block_types:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for block_type in block_types:
        value = _normalize_block_type_name(block_type)
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _build_block_type_condition(block_types: list[str] | None, params: dict) -> str | None:
    normalized = _normalize_block_types(block_types)
    if not normalized:
        return None
    params["block_types"] = normalized
    return "COALESCE(blk.block_type, dc.chunk_type) IN :block_types"


def _focused_block_types(query_intent: dict[str, object]) -> list[str]:
    primary = str(query_intent["primary"])
    if primary == "table":
        return ["table", "caption"]
    if primary == "image":
        return ["image", "caption"]
    if primary == "caption":
        return ["caption", "image", "table"]
    return []


def _build_access_conditions(search_scope: str, dept_id: int,
                             accessible_folder_ids: list[int], params: dict) -> str:
    """Build RBAC WHERE conditions. Shared by dense and sparse search."""
    if search_scope == "dept":
        params["dept_id"] = dept_id
        return "d.dept_id = :dept_id"
    elif search_scope == "folder":
        if not accessible_folder_ids:
            return "FALSE"
        params["folder_ids"] = list(accessible_folder_ids)
        return "d.folder_id = ANY(:folder_ids)"
    else:
        params["dept_id"] = dept_id
        if accessible_folder_ids:
            params["folder_ids"] = list(accessible_folder_ids)
            return "(d.dept_id = :dept_id OR d.folder_id = ANY(:folder_ids))"
        else:
            return "d.dept_id = :dept_id"


def dense_search(query_vector: list[float], dept_id: int, accessible_folder_ids: list[int],
                 search_scope: str = "all", limit: int = 20,
                 block_types: list[str] | None = None) -> list[dict]:
    vec_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    params = {"vec": vec_str, "lim": limit}

    conditions = ["dc.embedding IS NOT NULL", "d.status = 'indexed'"]
    access_cond = _build_access_conditions(search_scope, dept_id, accessible_folder_ids, params)
    conditions.append(access_cond)
    block_type_cond = _build_block_type_condition(block_types, params)
    if block_type_cond:
        conditions.append(block_type_cond)

    where = "WHERE " + " AND ".join(conditions)
    sql = text(f"""
        {_result_select("1 - (dc.embedding <=> CAST(:vec AS vector))", "dense_score")}
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
        LEFT JOIN doc_block blk ON dc.block_id = blk.block_id
        {where}
        ORDER BY dc.embedding <=> CAST(:vec AS vector)
        LIMIT :lim
    """)
    if params.get("block_types"):
        sql = sql.bindparams(bindparam("block_types", expanding=True))

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
    return [dict(r._mapping) for r in rows]


def sparse_search(query_text: str, dept_id: int, accessible_folder_ids: list[int],
                  search_scope: str = "all", limit: int = 20,
                  block_types: list[str] | None = None) -> list[dict]:
    params = {"query": query_text, "lim": limit}

    conditions = ["dc.tsv @@ plainto_tsquery('simple', :query)", "d.status = 'indexed'"]
    access_cond = _build_access_conditions(search_scope, dept_id, accessible_folder_ids, params)
    conditions.append(access_cond)
    block_type_cond = _build_block_type_condition(block_types, params)
    if block_type_cond:
        conditions.append(block_type_cond)

    where = "WHERE " + " AND ".join(conditions)
    sql = text(f"""
        {_result_select("ts_rank(dc.tsv, plainto_tsquery('simple', :query))", "sparse_score")}
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
        LEFT JOIN doc_block blk ON dc.block_id = blk.block_id
        {where}
        ORDER BY sparse_score DESC
        LIMIT :lim
    """)
    if params.get("block_types"):
        sql = sql.bindparams(bindparam("block_types", expanding=True))

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
    return [dict(r._mapping) for r in rows]


def keyword_search(query_terms: list[str], dept_id: int, accessible_folder_ids: list[int],
                   search_scope: str = "all", limit: int = 20,
                   block_types: list[str] | None = None) -> list[dict]:
    normalized_terms = [
        normalize_search_text(term)
        for term in query_terms
        if len(normalize_search_text(term)) >= 2
    ]
    normalized_terms = list(dict.fromkeys(normalized_terms))
    if not normalized_terms:
        return []

    params = {"terms": normalized_terms, "lim": limit}
    conditions = ["dk.normalized_keyword IN :terms", "d.status = 'indexed'"]
    access_cond = _build_access_conditions(search_scope, dept_id, accessible_folder_ids, params)
    conditions.append(access_cond)
    block_type_cond = _build_block_type_condition(block_types, params)
    if block_type_cond:
        conditions.append(block_type_cond)

    where = "WHERE " + " AND ".join(conditions)
    sql = (
        text(f"""
            {_result_select("SUM(dk.weight)", "keyword_score")}
            FROM doc_keyword dk
            JOIN doc_chunk dc ON dk.chunk_id = dc.chunk_id
            JOIN document d ON dc.doc_id = d.doc_id
            LEFT JOIN doc_block blk ON dc.block_id = blk.block_id
            {where}
            GROUP BY dc.chunk_id, dc.doc_id, dc.chunk_idx, dc.content,
                     dc.block_id, blk.block_type, dc.chunk_type,
                     blk.page_number, dc.page_number, blk.sheet_name,
                     blk.slide_number, blk.section_path, d.file_name, d.type, d.updated_at
            ORDER BY keyword_score DESC
            LIMIT :lim
        """)
        .bindparams(bindparam("terms", expanding=True))
    )
    if params.get("block_types"):
        sql = sql.bindparams(bindparam("block_types", expanding=True))

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
    return [dict(r._mapping) for r in rows]


def reciprocal_rank_fusion(*result_sets: list[dict], k: int = 60) -> list[dict]:
    scores = {}
    chunk_data = {}

    for result_set in result_sets:
        for rank, row in enumerate(result_set):
            cid = row["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
            if cid not in chunk_data:
                chunk_data[cid] = row
            else:
                chunk_data[cid].update({k_: v for k_, v in row.items() if k_ not in chunk_data[cid]})

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return [{**chunk_data[cid], "rrf_score": scores[cid]} for cid in sorted_ids]


def _normalize_block_type(block_type: str | None) -> str:
    return normalize_search_text(block_type or "text") or "text"


def _count_signal_hits(row: dict) -> int:
    return sum(
        1
        for field in ("dense_score", "sparse_score", "keyword_score")
        if row.get(field) not in (None, 0, 0.0)
    )


def _compute_freshness_boost(updated_at: datetime | None, recency_sensitive: bool) -> float:
    if not updated_at:
        return 0.0

    now = datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    age_days = max((now - updated_at).total_seconds() / 86400, 0)
    if recency_sensitive:
        if age_days <= 7:
            return 0.14
        if age_days <= 30:
            return 0.1
        if age_days <= 90:
            return 0.06
        if age_days <= 180:
            return 0.03
        return 0.0

    if age_days <= 30:
        return 0.02
    if age_days <= 90:
        return 0.01
    return 0.0


def apply_exact_match_boost(
    query_text: str,
    expanded_terms: list[str],
    results: list[dict],
    *,
    query_intent: dict[str, object],
) -> list[dict]:
    normalized_query = normalize_search_text(query_text)
    normalized_terms = [
        normalize_search_text(term)
        for term in expanded_terms
        if len(normalize_search_text(term)) >= 2
    ]
    normalized_terms = list(dict.fromkeys(normalized_terms))
    block_preferences = query_intent["preferences"]
    recency_sensitive = bool(query_intent["hints"].get("recency"))

    boosted = []
    for row in results:
        file_name_norm = normalize_search_text(row.get("file_name", ""))
        metadata_haystack = " ".join(
            str(part)
            for part in [
                row.get("file_name", ""),
                row.get("content", ""),
                row.get("section_path", ""),
                row.get("sheet_name", ""),
                row.get("slide_number", ""),
                row.get("page_number", ""),
                row.get("block_type", ""),
                row.get("file_type", ""),
            ]
            if part not in (None, "")
        )
        haystack = normalize_search_text(metadata_haystack)

        boost = 0.0
        if normalized_query and normalized_query in haystack:
            boost += 0.35
        if normalized_query and normalized_query in file_name_norm:
            boost += 0.2

        term_hits = sum(1 for term in normalized_terms if term in haystack)
        boost += min(term_hits * 0.06, 0.3)

        keyword_score = float(row.get("keyword_score") or 0.0)
        boost += min(keyword_score * 0.05, 0.25)

        block_type = _normalize_block_type(row.get("block_type") or row.get("chunk_type"))
        boost += block_preferences.get(block_type, 0.0)

        if block_type == "table" and "|" in row.get("content", ""):
            boost += 0.04
        if block_type == "caption" and row.get("page_number"):
            boost += 0.03
        if row.get("sheet_name") and "sheet" in haystack:
            boost += 0.03
        if row.get("slide_number") and any(term in normalized_query for term in ("slide", "슬라이드")):
            boost += 0.03

        signal_count = _count_signal_hits(row)
        multi_signal_boost = max(signal_count - 1, 0) * 0.04
        freshness_boost = _compute_freshness_boost(row.get("updated_at"), recency_sensitive)

        boost += multi_signal_boost
        boost += freshness_boost

        row["exact_match_boost"] = round(boost, 4)
        row["freshness_boost"] = round(freshness_boost, 4)
        row["multi_signal_boost"] = round(multi_signal_boost, 4)
        row["signal_count"] = signal_count
        row["retrieval_intent"] = str(query_intent["primary"])
        row["final_score"] = row.get("rrf_score", 0.0) + boost
        boosted.append(row)

    return sorted(boosted, key=lambda item: item.get("final_score", 0.0), reverse=True)


def apply_block_type_budgets(results: list[dict], budgets: dict[str, int], limit: int) -> list[dict]:
    if not results:
        return []
    if not budgets:
        return results[:limit]

    selected: list[dict] = []
    seen_chunk_ids: set[int] = set()

    def add_row(row: dict) -> None:
        chunk_id = row["chunk_id"]
        if chunk_id in seen_chunk_ids:
            return
        seen_chunk_ids.add(chunk_id)
        selected.append(row)

    for block_type, budget in budgets.items():
        if len(selected) >= limit:
            break
        remaining = budget
        for row in results:
            if len(selected) >= limit or remaining <= 0:
                break
            row_block_type = _normalize_block_type(row.get("block_type") or row.get("chunk_type"))
            if row_block_type != block_type:
                continue
            if row["chunk_id"] in seen_chunk_ids:
                continue
            add_row(row)
            remaining -= 1

    for row in results:
        if len(selected) >= limit:
            break
        add_row(row)

    return selected[:limit]


def hybrid_search(query_text: str, query_vector: list[float],
                  dept_id: int, accessible_folder_ids: list[int],
                  search_scope: str = "all", dense_limit: int = 20,
                  sparse_limit: int = 20, final_limit: int | None = None) -> list[dict]:
    with get_session() as session:
        alias_rows = get_alias_rows(session)

    base_terms = extract_candidate_terms(query_text)
    expanded_terms = expand_terms(base_terms + [query_text], alias_rows)
    sparse_query = " ".join(expanded_terms) if expanded_terms else query_text
    query_intent = classify_query_intent(query_text, expanded_terms)

    final_limit = final_limit or max(dense_limit, sparse_limit)
    candidate_limit = max(final_limit, dense_limit, sparse_limit) * int(query_intent["candidate_multiplier"])
    candidate_limit = min(
        max(candidate_limit, final_limit),
        serving_settings.retrieval_max_candidates,
    )
    focused_block_types = _focused_block_types(query_intent)
    focused_limit = min(
        max(
            final_limit * serving_settings.retrieval_focused_limit_multiplier,
            serving_settings.retrieval_focused_min_limit,
        ),
        candidate_limit,
    )

    result_sets = [
        dense_search(query_vector, dept_id, accessible_folder_ids, search_scope, candidate_limit),
        sparse_search(sparse_query, dept_id, accessible_folder_ids, search_scope, candidate_limit),
        keyword_search(expanded_terms, dept_id, accessible_folder_ids, search_scope, candidate_limit),
    ]

    if focused_block_types:
        result_sets.extend([
            dense_search(
                query_vector,
                dept_id,
                accessible_folder_ids,
                search_scope,
                focused_limit,
                block_types=focused_block_types,
            ),
            sparse_search(
                sparse_query,
                dept_id,
                accessible_folder_ids,
                search_scope,
                focused_limit,
                block_types=focused_block_types,
            ),
            keyword_search(
                expanded_terms,
                dept_id,
                accessible_folder_ids,
                search_scope,
                focused_limit,
                block_types=focused_block_types,
            ),
        ])

    fused = reciprocal_rank_fusion(*result_sets)
    boosted = apply_exact_match_boost(
        query_text,
        expanded_terms,
        fused,
        query_intent=query_intent,
    )
    return apply_block_type_budgets(boosted, query_intent["budgets"], final_limit)
