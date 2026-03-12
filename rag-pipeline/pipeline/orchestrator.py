import logging
from datetime import datetime, timezone

from shared.db import get_session
from shared.event_logger import get_event_logger
from shared.models.orm import Document, PipelineLog

from rag_pipeline.pipeline.parser import parse_document
from rag_pipeline.pipeline.chunker import chunk_text
from rag_pipeline.pipeline.embedder import embed_chunks
from rag_pipeline.pipeline.indexer import index_chunks
from rag_pipeline.pipeline.graph_extractor import extract_entities, store_entities

logger = logging.getLogger(__name__)
elog = get_event_logger("pipeline")


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
        file_name = doc.file_name

    elog.info("Pipeline started", doc_id=doc_id, details={"file": file_name, "path": file_path})

    try:
        # Stage 1: MinerU Parse
        with elog.timed("mineru_parse", doc_id=doc_id):
            log_stage(doc_id, "mineru_parse", "running")
            parse_result = parse_document(file_path)
            log_stage(doc_id, "mineru_parse", "success", metadata={"pages": parse_result.total_pages})
        elog.info("Parsed document", doc_id=doc_id,
                  details={"pages": parse_result.total_pages, "images": len(getattr(parse_result, 'images', []))})

        # Stage 2: Chunking
        with elog.timed("chunk", doc_id=doc_id):
            log_stage(doc_id, "chunk", "running")
            chunks = chunk_text(parse_result.raw_text)
            log_stage(doc_id, "chunk", "success", metadata={"count": len(chunks)})
        elog.info("Chunked document", doc_id=doc_id, details={"chunk_count": len(chunks)})

        if not chunks:
            with get_session() as session:
                d = session.query(Document).filter(Document.doc_id == doc_id).first()
                d.status = "indexed"
                d.total_page_cnt = parse_result.total_pages
            elog.info("Pipeline complete (no chunks)", doc_id=doc_id)
            return

        # Stage 3: Embedding
        with elog.timed("embed", doc_id=doc_id):
            log_stage(doc_id, "embed", "running")
            texts = [c["text"] for c in chunks]
            embeddings = embed_chunks(texts)
            log_stage(doc_id, "embed", "success")
        elog.info("Embedded chunks", doc_id=doc_id,
                  details={"chunk_count": len(chunks), "dim": len(embeddings[0]) if embeddings else 0})

        # Stage 4: Indexing
        with elog.timed("index", doc_id=doc_id):
            log_stage(doc_id, "index", "running")
            index_chunks(doc_id, chunks, embeddings)
            log_stage(doc_id, "index", "success")

        # Stage 5: Graph Extraction
        with elog.timed("graph_extract", doc_id=doc_id):
            log_stage(doc_id, "graph_extract", "running")
            all_text = " ".join(texts)
            entities = extract_entities(all_text)
            store_entities(doc_id, entities)
            log_stage(doc_id, "graph_extract", "success", metadata={"entities": len(entities)})
        elog.info("Extracted entities", doc_id=doc_id, details={"entity_count": len(entities)})

        with get_session() as session:
            d = session.query(Document).filter(Document.doc_id == doc_id).first()
            d.status = "indexed"
            d.total_page_cnt = parse_result.total_pages

        elog.info("Pipeline complete", doc_id=doc_id, details={
            "file": file_name,
            "pages": parse_result.total_pages,
            "chunks": len(chunks),
            "entities": len(entities),
        })

    except Exception as e:
        # Log failed stage to pipeline_logs
        with get_session() as session:
            d = session.query(Document).filter(Document.doc_id == doc_id).first()
            if d:
                d.status = "failed"
                d.error_msg = str(e)[:1000]

        elog.error("Pipeline failed", doc_id=doc_id, error=e,
                   details={"file": file_name})
        raise
