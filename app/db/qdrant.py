import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
)

from app.config import settings

logger = logging.getLogger(__name__)


class QdrantManager:
    def __init__(self):
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        self.collection = settings.qdrant_collection
        self._ensure_collection()

    def _ensure_collection(self):
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection not in collections:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection: %s", self.collection)

    def upsert_vectors(self, points: list[PointStruct]):
        self.client.upsert(
            collection_name=self.collection,
            points=points,
        )
        logger.info("Upserted %d vectors", len(points))

    def delete_by_doc_id(self, doc_id: int):
        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
        logger.info("Deleted vectors for doc_id=%d", doc_id)

    def search(
        self,
        vector: list[float],
        limit: int = 5,
        doc_id_filter: Optional[int] = None,
    ):
        query_filter = None
        if doc_id_filter is not None:
            query_filter = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id_filter))]
            )

        return self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=limit,
        )
