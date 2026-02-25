import hashlib
import logging
from pathlib import Path

from app.config import settings
from app.db.models import Document, DocChunk
from app.db.postgres import get_session
from app.parsers import get_parser
from app.processing.chunker import chunk_text
from app.processing.embedder import embed_chunks

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def ingest_document(
    file_path: str,
    folder_id: int | None = None,
    dept_id: int = 1,
    role_id: int = 3,
) -> int:
    """Full ingestion pipeline for a single document.

    Returns the doc_id (integer) of the created document record.
    """
    path = Path(file_path)
    file_hash = compute_file_hash(file_path)
    file_size = path.stat().st_size
    file_type = path.suffix.lstrip(".").lower()

    with get_session() as session:
        # Check if document with same hash already exists
        existing = session.query(Document).filter(Document.hash == file_hash).first()
        if existing:
            logger.info("Document already indexed (hash=%s): %s", file_hash[:12], path.name)
            return existing.doc_id

        # Create document record
        doc = Document(
            folder_id=folder_id,
            file_name=path.name,
            path=str(path),
            type=file_type,
            hash=file_hash,
            size=file_size,
            dept_id=dept_id,
            role_id=role_id,
            status="processing",
        )
        session.add(doc)
        session.flush()  # Get doc_id
        doc_id = doc.doc_id

        try:
            # 1. Parse
            parser = get_parser(file_path)
            result = parser.parse(file_path)
            logger.info("Parsed %s: %d pages", path.name, result.total_pages)

            # 2. Chunk
            chunks = chunk_text(result.raw_text)
            if not chunks:
                doc.status = "indexed"
                doc.total_page_cnt = result.total_pages
                logger.warning("No chunks produced for %s", path.name)
                return doc_id

            # 3. Embed
            texts = [c["text"] for c in chunks]
            embeddings = embed_chunks(texts)
            logger.info("Embedded %d chunks for %s", len(chunks), path.name)

            # 4. Store in PostgreSQL (chunks + vectors in same table)
            chunk_records = []
            for chunk, embedding in zip(chunks, embeddings):
                chunk_records.append(
                    DocChunk(
                        doc_id=doc_id,
                        chunk_idx=chunk["chunk_idx"],
                        content=chunk["text"],
                        token_cnt=chunk["token_cnt"],
                        page_number=_find_page_for_chunk(result, chunk["text"]),
                        embedding=embedding.tolist(),
                        embed_model=settings.embed_model,
                    )
                )

            session.add_all(chunk_records)

            doc.status = "indexed"
            doc.total_page_cnt = result.total_pages
            logger.info(
                "Ingested %s: doc_id=%d, chunks=%d", path.name, doc_id, len(chunks)
            )

        except Exception as e:
            doc.status = "failed"
            doc.error_msg = str(e)[:1000]
            logger.error("Failed to ingest %s: %s", path.name, e)
            raise

    return doc_id


def _find_page_for_chunk(result, chunk_text: str) -> int | None:
    """Try to find which page a chunk belongs to."""
    for page in result.pages:
        if chunk_text[:100] in page.text:
            return page.page_num
    return None
