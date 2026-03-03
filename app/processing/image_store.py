"""Image storage: moves extracted images to permanent storage."""

import logging
import shutil
from pathlib import Path

from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


def save_images_for_document(
    doc_id: int,
    extracted_images: list,
) -> list[dict]:
    """Move extracted images to /data/images/{doc_id}/ and return metadata.

    Returns list of dicts with permanent_path, image_type, page_num, width, height.
    """
    dest_dir = Path(settings.image_store_dir) / str(doc_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for idx, img in enumerate(extracted_images):
        src = Path(img.temp_path)
        if not src.exists():
            logger.warning("Temp image not found, skipping: %s", src)
            continue

        ext = img.image_type or src.suffix.lstrip(".")
        dest = dest_dir / f"img_{idx:04d}.{ext}"
        shutil.copy2(str(src), str(dest))

        width, height = None, None
        try:
            with Image.open(dest) as pil_img:
                width, height = pil_img.size
        except Exception:
            pass

        results.append({
            "permanent_path": str(dest),
            "image_type": ext,
            "page_num": img.page_num,
            "width": width,
            "height": height,
        })

    return results


def delete_images_for_document(doc_id: int):
    """Remove all images for a document from disk."""
    dest_dir = Path(settings.image_store_dir) / str(doc_id)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
        logger.info("Deleted image directory: %s", dest_dir)
