import hashlib
import logging
import shutil
from pathlib import Path

from app.config import settings
from app.db.models import Document, DocChunk, DocImage
from app.db.postgres import get_session
from app.parsers import get_parser
from app.processing.chunker import chunk_text, token_length
from app.processing.embedder import embed_chunks
from app.processing.image_store import save_images_for_document

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

            # 2. Save images to disk + create DocImage records
            image_records = []
            if result.images:
                saved = save_images_for_document(doc_id, result.images)
                for s in saved:
                    img_rec = DocImage(
                        doc_id=doc_id,
                        page_number=s["page_num"],
                        image_path=s["permanent_path"],
                        image_type=s["image_type"],
                        width=s["width"],
                        height=s["height"],
                    )
                    session.add(img_rec)
                    session.flush()  # get image_id
                    image_records.append(img_rec)
                logger.info("Saved %d images for %s", len(image_records), path.name)

            # 3. VLM description + embedding (if enabled)
            if settings.enable_image_embedding and image_records:
                _process_image_descriptions(session, doc_id, image_records)

            # 4. Chunk text
            chunks = chunk_text(result.raw_text)
            if not chunks and not image_records:
                doc.status = "indexed"
                doc.total_page_cnt = result.total_pages
                logger.warning("No chunks produced for %s", path.name)
                return doc_id

            # 5. Embed text chunks
            if chunks:
                texts = [c["text"] for c in chunks]
                embeddings = embed_chunks(texts)
                logger.info("Embedded %d chunks for %s", len(chunks), path.name)

                # 6. Store in PostgreSQL
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
                            chunk_type="text",
                        )
                    )
                session.add_all(chunk_records)

            doc.status = "indexed"
            doc.total_page_cnt = result.total_pages
            logger.info(
                "Ingested %s: doc_id=%d, chunks=%d, images=%d",
                path.name, doc_id, len(chunks), len(image_records),
            )

        except Exception as e:
            doc.status = "failed"
            doc.error_msg = str(e)[:1000]
            logger.error("Failed to ingest %s: %s", path.name, e)
            raise
        finally:
            # Cleanup MinerU temp output directory
            mineru_dir = result.metadata.get("mineru_output_dir") if hasattr(result, "metadata") else None
            if mineru_dir and Path(mineru_dir).is_dir():
                shutil.rmtree(mineru_dir, ignore_errors=True)

    return doc_id


def _process_image_descriptions(session, doc_id: int, image_records: list[DocImage]):
    """Generate VLM descriptions for images and create embedding chunks."""
    from app.processing.vlm_client import describe_image

    for img_rec in image_records:
        description = describe_image(img_rec.image_path)
        if not description:
            continue

        img_rec.description = description

        # Embed the description and store as a special chunk
        desc_embeddings = embed_chunks([description])
        desc_chunk = DocChunk(
            doc_id=doc_id,
            chunk_idx=10000 + img_rec.image_id,
            content=description,
            token_cnt=token_length(description),
            page_number=img_rec.page_number,
            embedding=desc_embeddings[0].tolist(),
            embed_model=settings.embed_model,
            chunk_type="image_description",
            image_id=img_rec.image_id,
        )
        session.add(desc_chunk)

    logger.info("Processed VLM descriptions for doc_id=%d", doc_id)


def _find_page_for_chunk(result, chunk_text: str) -> int | None:
    """Try to find which page a chunk belongs to."""
    for page in result.pages:
        if chunk_text[:100] in page.text:
            return page.page_num
    return None
