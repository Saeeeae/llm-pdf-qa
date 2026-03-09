import logging

from shared.db import get_session
from shared.models.orm import Document

logger = logging.getLogger(__name__)


def get_pending_doc_ids() -> list[int]:
    """Get all document IDs that need processing (status='pending')."""
    with get_session() as session:
        docs = (
            session.query(Document.doc_id)
            .filter(Document.status.in_(["pending"]))
            .all()
        )
    doc_ids = [d.doc_id for d in docs]
    logger.info("Found %d pending documents", len(doc_ids))
    return doc_ids


def get_failed_doc_ids() -> list[int]:
    """Get all failed document IDs for retry."""
    with get_session() as session:
        docs = (
            session.query(Document.doc_id)
            .filter(Document.status == "failed")
            .all()
        )
    return [d.doc_id for d in docs]


def reset_failed_documents(doc_ids: list[int] | None = None) -> int:
    """Reset failed documents to pending for retry.

    If *doc_ids* is ``None``, all failed documents are reset.
    Returns the number of documents that were reset.
    """
    with get_session() as session:
        query = session.query(Document).filter(Document.status == "failed")
        if doc_ids:
            query = query.filter(Document.doc_id.in_(doc_ids))
        count = query.update({"status": "pending", "error_msg": None})
    logger.info("Reset %d failed documents to pending", count)
    return count
