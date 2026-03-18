import logging
import shutil
from pathlib import Path

from rag_pipeline.config import pipeline_settings
from shared.db import get_session
from shared.models.orm import DocImage

logger = logging.getLogger(__name__)


def sync_document_images(doc_id: int, images: list) -> tuple[int, dict[int, int]]:
    """Persist extracted images into IMAGE_STORE_DIR and doc_image.

    Returns (count, {image_index: image_id}).
    """
    target_root = Path(pipeline_settings.image_store_dir) / str(doc_id)
    target_root.mkdir(parents=True, exist_ok=True)

    with get_session() as session:
        session.query(DocImage).filter(DocImage.doc_id == doc_id).delete()

        count = 0
        image_id_map: dict[int, int] = {}
        for idx, image in enumerate(images, start=1):
            source = Path(image.temp_path)
            suffix = source.suffix or f".{image.image_type}"
            target = target_root / f"page-{(image.page_num or 1):04d}-img-{idx:03d}{suffix}"

            try:
                if source.resolve() != target.resolve():
                    shutil.copy2(source, target)
            except FileNotFoundError:
                logger.warning("Extracted image missing before persistence: %s", source)
                continue

            record = DocImage(
                doc_id=doc_id,
                page_number=image.page_num,
                image_path=str(target),
                image_type=image.image_type,
                width=image.width,
                height=image.height,
            )
            session.add(record)
            session.flush()
            image_id_map[idx] = record.image_id
            count += 1

    logger.info("Persisted %d images for doc_id=%d", count, doc_id)
    return count, image_id_map
