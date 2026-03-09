import logging
from datetime import datetime, timezone

from shared.db import get_session
from shared.models.orm import Document, PipelineLog

from rag_pipeline.pipeline.parser import parse_document
from rag_pipeline.pipeline.chunker import chunk_text
from rag_pipeline.pipeline.embedder import embed_chunks
from rag_pipeline.pipeline.indexer import index_chunks
from rag_pipeline.pipeline.graph_extractor import extract_entities, store_entities

logger = logging.getLogger(__name__)


def log_stage(doc_id: int, stage: str, status: str, error: str = None, metadata: dict = None):
    with get_session() as session:
        log = PipelineLog(
            doc_id=doc_id, stage=stage, status=status,
            error_message=error, metadata_=metadata,
        )
        if status in ("success", "failed"):
            log.finished_at = datetime.now(timezone.utc)
        session.add(log)


def process_document(doc_id: int):
    with get_session() as session:
        doc = session.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found")
        doc.status = "processing"
        file_path = doc.path

    try:
        log_stage(doc_id, "mineru_parse", "running")
        parse_result = parse_document(file_path)
        log_stage(doc_id, "mineru_parse", "success", metadata={"pages": parse_result.total_pages})

        log_stage(doc_id, "chunk", "running")
        chunks = chunk_text(parse_result.raw_text)
        log_stage(doc_id, "chunk", "success", metadata={"count": len(chunks)})

        if not chunks:
            with get_session() as session:
                d = session.query(Document).filter(Document.doc_id == doc_id).first()
                d.status = "indexed"
                d.total_page_cnt = parse_result.total_pages
            return

        log_stage(doc_id, "embed", "running")
        texts = [c["text"] for c in chunks]
        embeddings = embed_chunks(texts)
        log_stage(doc_id, "embed", "success")

        log_stage(doc_id, "index", "running")
        index_chunks(doc_id, chunks, embeddings)
        log_stage(doc_id, "index", "success")

        log_stage(doc_id, "graph_extract", "running")
        all_text = " ".join(texts)
        entities = extract_entities(all_text)
        store_entities(doc_id, entities)
        log_stage(doc_id, "graph_extract", "success", metadata={"entities": len(entities)})

        with get_session() as session:
            d = session.query(Document).filter(Document.doc_id == doc_id).first()
            d.status = "indexed"
            d.total_page_cnt = parse_result.total_pages

        logger.info("Pipeline complete for doc_id=%d", doc_id)

    except Exception as e:
        with get_session() as session:
            d = session.query(Document).filter(Document.doc_id == doc_id).first()
            if d:
                d.status = "failed"
                d.error_msg = str(e)[:1000]
        logger.error("Pipeline failed for doc_id=%d: %s", doc_id, e)
        raise
