"""pgvector-based vector store using PostgreSQL.

Replaces Qdrant — all vectors are stored in doc_chunk.embedding column.
"""

import logging

import numpy as np
from sqlalchemy import text

from app.db.postgres import get_session

logger = logging.getLogger(__name__)


def upsert_chunk_vectors(chunk_ids: list[int], embeddings: np.ndarray):
    """Update embedding column for existing doc_chunk rows."""
    with get_session() as session:
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            session.execute(
                text("UPDATE doc_chunk SET embedding = :vec WHERE chunk_id = :cid"),
                {"vec": embedding.tolist(), "cid": chunk_id},
            )
        logger.info("Updated embeddings for %d chunks", len(chunk_ids))


def delete_vectors_by_doc_id(doc_id: int):
    """Clear embedding column for all chunks of a document.

    Chunk rows themselves are deleted via CASCADE when document is deleted,
    so this is only needed if you want to clear vectors without deleting chunks.
    """
    with get_session() as session:
        session.execute(
            text("UPDATE doc_chunk SET embedding = NULL WHERE doc_id = :did"),
            {"did": doc_id},
        )


def search_similar(
    query_vector: list[float],
    limit: int = 5,
    doc_id_filter: int | None = None,
    user_dept_id: int | None = None,
    user_auth_level: int | None = None,
    accessible_folder_ids: list[int] | None = None,
    search_scope: str = "all",
) -> list[dict]:
    """Cosine similarity search with RBAC filtering.

    search_scope:
      "all"    — filter by role auth_level only
      "dept"   — restrict to user's department documents
      "folder" — restrict to accessible_folder_ids
    """
    params: dict = {"vec": query_vector, "lim": limit}

    conditions = ["dc.embedding IS NOT NULL", "d.status = 'indexed'"]

    if user_auth_level is not None:
        conditions.append("r.auth_level <= :auth_level")
        params["auth_level"] = user_auth_level

    if search_scope == "dept" and user_dept_id is not None:
        conditions.append("d.dept_id = :dept_id")
        params["dept_id"] = user_dept_id
    elif search_scope == "folder" and accessible_folder_ids:
        conditions.append("d.folder_id = ANY(:folder_ids)")
        params["folder_ids"] = accessible_folder_ids

    if doc_id_filter is not None:
        conditions.append("dc.doc_id = :did")
        params["did"] = doc_id_filter

    where_clause = "WHERE " + " AND ".join(conditions)

    sql = text(f"""
        SELECT
            dc.chunk_id,
            dc.doc_id,
            dc.chunk_idx,
            dc.content,
            dc.chunk_type,
            dc.page_number,
            1 - (dc.embedding <=> :vec::vector) AS score,
            d.file_name,
            di.image_id,
            di.image_path,
            di.image_type
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
        JOIN roles r ON d.role_id = r.role_id
        LEFT JOIN doc_image di ON dc.image_id = di.image_id
        {where_clause}
        ORDER BY dc.embedding <=> :vec::vector
        LIMIT :lim
    """)

    with get_session() as session:
        rows = session.execute(sql, params).fetchall()

    return [
        {
            "chunk_id": r.chunk_id,
            "doc_id": r.doc_id,
            "chunk_idx": r.chunk_idx,
            "text": r.content[:500],
            "chunk_type": r.chunk_type or "text",
            "page_number": r.page_number,
            "score": float(r.score),
            "file_name": r.file_name,
            "image_id": r.image_id,
            "image_path": r.image_path,
        }
        for r in rows
    ]
