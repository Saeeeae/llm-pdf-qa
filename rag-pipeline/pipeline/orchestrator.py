import logging
from datetime import datetime, timezone

from shared.db import get_session
from shared.event_logger import get_event_logger
from shared.models.orm import Document, PipelineLog

from rag_pipeline.pipeline.parser import parse_document
from rag_pipeline.pipeline.chunker import chunk_text
from rag_pipeline.pipeline.embedder import embed_chunks
from rag_pipeline.pipeline.indexer import index_chunks
from rag_pipeline.pipeline.image_store import sync_document_images
from rag_pipeline.pipeline.graph_extractor import extract_entities, store_entities

logger = logging.getLogger(__name__)
elog = get_event_logger("pipeline")


def log_stage(doc_id: int, stage: str, status: str, error: str = None, metadata: dict = None):
    with get_session() as session:
        if status == "running":
            session.add(PipelineLog(
                doc_id=doc_id,
                stage=stage,
                status=status,
                error_message=error,
                metadata_=metadata,
            ))
            return

        log = (
            session.query(PipelineLog)
            .filter(
                PipelineLog.doc_id == doc_id,
                PipelineLog.stage == stage,
                PipelineLog.status == "running",
                PipelineLog.finished_at.is_(None),
            )
            .order_by(PipelineLog.started_at.desc())
            .first()
        )

        if log:
            log.status = status
            log.error_message = error
            log.metadata_ = metadata
            log.finished_at = datetime.now(timezone.utc)
        else:
            session.add(PipelineLog(
                doc_id=doc_id,
                stage=stage,
                status=status,
                error_message=error,
                metadata_=metadata,
                finished_at=datetime.now(timezone.utc),
            ))


def process_document(doc_id: int):
    with get_session() as session:
        doc = session.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found")
        doc.status = "processing"
        doc.error_msg = None
        file_path = doc.path
        file_name = doc.file_name

    elog.info("Pipeline started", doc_id=doc_id, details={"file": file_name, "path": file_path})
    current_stage = "mineru_parse"

    try:
        # Stage 1: MinerU Parse
        current_stage = "mineru_parse"
        with elog.timed("mineru_parse", doc_id=doc_id):
            log_stage(doc_id, "mineru_parse", "running")
            parse_result = parse_document(file_path)
            stored_image_count = sync_document_images(doc_id, parse_result.images)
            log_stage(doc_id, "mineru_parse", "success", metadata={
                "pages": parse_result.total_pages,
                "images": stored_image_count,
            })
        elog.info("Parsed document", doc_id=doc_id,
                  details={"pages": parse_result.total_pages, "images": stored_image_count})

        # Stage 2: Chunking
        current_stage = "chunk"
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
                d.error_msg = None
            elog.info("Pipeline complete (no chunks)", doc_id=doc_id)
            return

        # Stage 3: Embedding
        current_stage = "embed"
        with elog.timed("embed", doc_id=doc_id):
            log_stage(doc_id, "embed", "running")
            texts = [c["text"] for c in chunks]
            embeddings = embed_chunks(texts)
            log_stage(doc_id, "embed", "success")
        embedding_count = len(embeddings) if embeddings is not None else 0
        embedding_dim = len(embeddings[0]) if embedding_count > 0 else 0
        elog.info("Embedded chunks", doc_id=doc_id,
                  details={"chunk_count": len(chunks), "embedding_count": embedding_count, "dim": embedding_dim})

        # Stage 4: Indexing
        current_stage = "index"
        with elog.timed("index", doc_id=doc_id):
            log_stage(doc_id, "index", "running")
            index_chunks(doc_id, chunks, embeddings)
            log_stage(doc_id, "index", "success")

        # Stage 5: Graph Extraction
        current_stage = "graph_extract"
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
            d.error_msg = None

        elog.info("Pipeline complete", doc_id=doc_id, details={
            "file": file_name,
            "pages": parse_result.total_pages,
            "chunks": len(chunks),
            "entities": len(entities),
        })

    except Exception as e:
        log_stage(
            doc_id,
            current_stage,
            "failed",
            error=str(e)[:1000],
            metadata={"file": file_name},
        )
        with get_session() as session:
            d = session.query(Document).filter(Document.doc_id == doc_id).first()
            if d:
                d.status = "failed"
                d.error_msg = str(e)[:1000]

        elog.error("Pipeline failed", doc_id=doc_id, error=e,
                   details={"file": file_name})
        raise
