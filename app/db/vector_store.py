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
) -> list[dict]:
    """Cosine similarity search using pgvector.

    Returns list of dicts with: chunk_id, doc_id, chunk_idx, content, score, file_name.
    """
    params: dict = {"vec": query_vector, "lim": limit}

    where_clause = "WHERE dc.embedding IS NOT NULL"
    if doc_id_filter is not None:
        where_clause += " AND dc.doc_id = :did"
        params["did"] = doc_id_filter

    sql = text(f"""
        SELECT
            dc.chunk_id,
            dc.doc_id,
            dc.chunk_idx,
            dc.content,
            1 - (dc.embedding <=> :vec::vector) AS score,
            d.file_name
        FROM doc_chunk dc
        JOIN document d ON dc.doc_id = d.doc_id
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
            "score": float(r.score),
            "file_name": r.file_name,
        }
        for r in rows
    ]
