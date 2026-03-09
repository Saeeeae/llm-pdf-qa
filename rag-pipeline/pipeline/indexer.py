import logging
from shared.db import get_session
from shared.models.orm import DocChunk

logger = logging.getLogger(__name__)


def index_chunks(doc_id: int, chunks: list[dict], embeddings, embed_model: str = "BAAI/bge-m3") -> int:
    with get_session() as session:
        session.query(DocChunk).filter(DocChunk.doc_id == doc_id).delete()
        records = []
        for chunk, emb in zip(chunks, embeddings):
            records.append(DocChunk(
                doc_id=doc_id,
                chunk_idx=chunk["chunk_idx"],
                content=chunk["text"],
                token_cnt=chunk["token_cnt"],
                page_number=chunk.get("page_number"),
                embedding=emb.tolist(),
                embed_model=embed_model,
                chunk_type=chunk.get("chunk_type", "text"),
            ))
        session.add_all(records)
    logger.info("Indexed %d chunks for doc_id=%d", len(records), doc_id)
    return len(records)
