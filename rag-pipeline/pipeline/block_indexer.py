import logging

from shared.db import get_session
from shared.models.orm import DocBlock
from shared.search_terms import normalize_search_text

logger = logging.getLogger(__name__)


def sync_document_blocks(doc_id: int, blocks: list, image_id_map: dict[int, int] | None = None) -> dict[int, int]:
    """Persist parse blocks and return a local-index to block_id map."""
    if not blocks:
        with get_session() as session:
            session.query(DocBlock).filter(DocBlock.doc_id == doc_id).delete()
        return {}

    with get_session() as session:
        session.query(DocBlock).filter(DocBlock.doc_id == doc_id).delete()

        records: list[DocBlock] = []
        for block_idx, block in enumerate(blocks):
            records.append(
                DocBlock(
                    doc_id=doc_id,
                    block_idx=block_idx,
                    block_type=block.block_type,
                    page_number=block.page_number,
                    sheet_name=block.sheet_name,
                    slide_number=block.slide_number,
                    section_path=block.section_path,
                    language=block.language,
                    bbox=block.bbox,
                    source_text=block.source_text,
                    normalized_text=normalize_search_text(block.source_text),
                    image_id=image_id_map.get(block.metadata.get("image_index")) if image_id_map else None,
                    metadata_json=block.metadata or None,
                )
            )

        session.add_all(records)
        session.flush()

        block_id_map = {record.block_idx: record.block_id for record in records}

        for block, record in zip(blocks, records):
            if block.parent_local_idx is not None:
                record.parent_block_id = block_id_map.get(block.parent_local_idx)

    logger.info("Indexed %d blocks for doc_id=%d", len(blocks), doc_id)
    return block_id_map
