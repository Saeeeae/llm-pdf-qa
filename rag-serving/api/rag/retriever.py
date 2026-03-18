import logging
from sqlalchemy import bindparam, text
from shared.db import get_session
from shared.search_terms import extract_candidate_terms, expand_terms, get_alias_rows, normalize_search_text

logger = logging.getLogger(__name__)

TABLE_HINTS = {"table", "표", "sheet", "excel", "엑셀", "row", "column", "행", "열", "셀"}
IMAGE_HINTS = {"image", "figure", "fig", "chart", "diagram", "사진", "이미지", "그림", "도표", "차트"}
CAPTION_HINTS = {"caption", "캡션", "figure legend", "table legend", "legend"}
SLIDE_HINTS = {"slide", "slides", "슬라이드", "deck", "ppt", "pptx"}
PAGE_HINTS = {"page", "pages", "페이지"}


def _result_select(score_expression: str, score_alias: str) -> str:
    return f"""
        SELECT dc.chunk_id, dc.doc_id, dc.block_id, dc.chunk_idx, dc.content,
               COALESCE(blk.block_type, dc.chunk_type) AS block_type,
               dc.chunk_type, COALESCE(blk.page_number, dc.page_number) AS page_number,
               blk.sheet_name, blk.slide_number, blk.section_path,
               {score_expression} AS {score_alias},
               d.file_name, d.type AS file_type
    """


def infer_block_type_preferences(query_text: str, expanded_terms: list[str]) -> dict[str, float]:
    normalized = normalize_search_text(" ".join([query_text, *expanded_terms]))
    preferences = {"text": 0.0, "table": 0.0, "image": 0.0, "caption": 0.0}

    if any(term in normalized for term in TABLE_HINTS):
        preferences["table"] = 0.28
        preferences["caption"] = max(preferences["caption"], 0.08)
    if any(term in normalized for term in IMAGE_HINTS):
        preferences["image"] = 0.24
        preferences["caption"] = max(preferences["caption"], 0.16)
    if any(term in normalized for term in CAPTION_HINTS):
        preferences["caption"] = max(preferences["caption"], 0.24)
    if any(term in normalized for term in SLIDE_HINTS):
        preferences["text"] = max(preferences["text"], 0.06)
        preferences["caption"] = max(preferences["caption"], 0.1)
    if any(term in normalized for term in PAGE_HINTS):
        preferences["text"] = max(preferences["text"], 0.04)

    return preferences


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
                 search_scope: str = "all", limit: int = 20) -> list[dict]:
    vec_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    params = {"vec": vec_str, "lim": limit}

    conditions = ["dc.embedding IS NOT NULL", "d.status = 'indexed'"]
    access_cond = _build_access_conditions(search_scope, dept_id, accessible_folder_ids, params)
    conditions.append(access_cond)

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

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
    return [dict(r._mapping) for r in rows]


def sparse_search(query_text: str, dept_id: int, accessible_folder_ids: list[int],
                  search_scope: str = "all", limit: int = 20) -> list[dict]:
    params = {"query": query_text, "lim": limit}

    conditions = ["dc.tsv @@ plainto_tsquery('simple', :query)", "d.status = 'indexed'"]
    access_cond = _build_access_conditions(search_scope, dept_id, accessible_folder_ids, params)
    conditions.append(access_cond)

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

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
    return [dict(r._mapping) for r in rows]


def keyword_search(query_terms: list[str], dept_id: int, accessible_folder_ids: list[int],
                   search_scope: str = "all", limit: int = 20) -> list[dict]:
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
                     blk.slide_number, blk.section_path, d.file_name, d.type
            ORDER BY keyword_score DESC
            LIMIT :lim
        """)
        .bindparams(bindparam("terms", expanding=True))
    )

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


def apply_exact_match_boost(query_text: str, expanded_terms: list[str], results: list[dict]) -> list[dict]:
    normalized_query = normalize_search_text(query_text)
    normalized_terms = [
        normalize_search_text(term)
        for term in expanded_terms
        if len(normalize_search_text(term)) >= 2
    ]
    normalized_terms = list(dict.fromkeys(normalized_terms))
    block_preferences = infer_block_type_preferences(query_text, expanded_terms)

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

        block_type = normalize_search_text(row.get("block_type") or row.get("chunk_type") or "text")
        boost += block_preferences.get(block_type, 0.0)

        if block_type == "table" and "|" in row.get("content", ""):
            boost += 0.04
        if block_type == "caption" and row.get("page_number"):
            boost += 0.03
        if row.get("sheet_name") and "sheet" in haystack:
            boost += 0.03
        if row.get("slide_number") and any(term in normalized_query for term in ("slide", "슬라이드")):
            boost += 0.03

        row["exact_match_boost"] = round(boost, 4)
        row["final_score"] = row.get("rrf_score", 0.0) + boost
        boosted.append(row)

    return sorted(boosted, key=lambda item: item.get("final_score", 0.0), reverse=True)


def hybrid_search(query_text: str, query_vector: list[float],
                  dept_id: int, accessible_folder_ids: list[int],
                  search_scope: str = "all", dense_limit: int = 20,
                  sparse_limit: int = 20) -> list[dict]:
    with get_session() as session:
        alias_rows = get_alias_rows(session)

    base_terms = extract_candidate_terms(query_text)
    expanded_terms = expand_terms(base_terms + [query_text], alias_rows)
    sparse_query = " ".join(expanded_terms) if expanded_terms else query_text

    dense = dense_search(query_vector, dept_id, accessible_folder_ids, search_scope, dense_limit)
    sparse = sparse_search(sparse_query, dept_id, accessible_folder_ids, search_scope, sparse_limit)
    keyword = keyword_search(expanded_terms, dept_id, accessible_folder_ids, search_scope, sparse_limit)
    fused = reciprocal_rank_fusion(dense, sparse, keyword)
    return apply_exact_match_boost(query_text, expanded_terms, fused)
