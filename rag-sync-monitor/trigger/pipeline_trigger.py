import logging

import httpx

from shared.db import get_session
from shared.models.orm import Document

logger = logging.getLogger(__name__)

PIPELINE_API_URL = "http://rag-pipeline:8001"


def trigger_pending_documents(pipeline_url: str = PIPELINE_API_URL) -> None:
    """Find all pending documents and send them to the pipeline service."""
    with get_session() as session:
        docs = (
            session.query(Document.doc_id)
            .filter(Document.status.in_(["pending"]))
            .all()
        )
        doc_ids = [d.doc_id for d in docs]

    if not doc_ids:
        logger.info("No pending documents to process")
        return

    response = httpx.post(
        f"{pipeline_url}/pipeline/trigger",
        json={"doc_ids": doc_ids},
        timeout=30.0,
    )
    response.raise_for_status()
    logger.info("Triggered pipeline for %d documents", len(doc_ids))


def trigger_specific_documents(
    doc_ids: list[int],
    pipeline_url: str = PIPELINE_API_URL,
) -> None:
    """Trigger the pipeline for a specific list of document IDs."""
    if not doc_ids:
        return

    response = httpx.post(
        f"{pipeline_url}/pipeline/trigger",
        json={"doc_ids": doc_ids},
        timeout=30.0,
    )
    response.raise_for_status()
    logger.info("Triggered pipeline for %d documents", len(doc_ids))
