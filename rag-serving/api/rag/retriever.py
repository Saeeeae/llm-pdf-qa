import logging
from sqlalchemy import text
from shared.db import get_session

logger = logging.getLogger(__name__)


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
        SELECT dc.chunk_id, dc.doc_id, dc.chunk_idx, dc.content,
               dc.chunk_type, dc.page_number,
               1 - (dc.embedding <=> CAST(:vec AS vector)) AS dense_score,
               d.file_name
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
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
        SELECT dc.chunk_id, dc.doc_id, dc.chunk_idx, dc.content,
               dc.chunk_type, dc.page_number,
               ts_rank(dc.tsv, plainto_tsquery('simple', :query)) AS sparse_score,
               d.file_name
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
        {where}
        ORDER BY sparse_score DESC
        LIMIT :lim
    """)

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()
    return [dict(r._mapping) for r in rows]


def reciprocal_rank_fusion(dense_results: list[dict], sparse_results: list[dict], k: int = 60) -> list[dict]:
    scores = {}
    chunk_data = {}

    for rank, row in enumerate(dense_results):
        cid = row["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        chunk_data[cid] = row

    for rank, row in enumerate(sparse_results):
        cid = row["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1 / (k + rank + 1)
        if cid not in chunk_data:
            chunk_data[cid] = row

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return [{**chunk_data[cid], "rrf_score": scores[cid]} for cid in sorted_ids]


def hybrid_search(query_text: str, query_vector: list[float],
                  dept_id: int, accessible_folder_ids: list[int],
                  search_scope: str = "all", dense_limit: int = 20,
                  sparse_limit: int = 20) -> list[dict]:
    dense = dense_search(query_vector, dept_id, accessible_folder_ids, search_scope, dense_limit)
    sparse = sparse_search(query_text, dept_id, accessible_folder_ids, search_scope, sparse_limit)
    return reciprocal_rank_fusion(dense, sparse)
