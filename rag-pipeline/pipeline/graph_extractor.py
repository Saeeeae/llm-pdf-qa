import logging
from neo4j import GraphDatabase
from shared.config import shared_settings
from shared.db import get_session
from shared.models.orm import GraphEntity

logger = logging.getLogger(__name__)


def get_neo4j_driver():
    return GraphDatabase.driver(
        shared_settings.neo4j_url,
        auth=(shared_settings.neo4j_user, shared_settings.neo4j_password),
    )


def extract_entities(text: str) -> list[dict]:
    # Phase 1: placeholder - implement with spaCy or LLM NER later
    entities = []
    return entities


def store_entities(doc_id: int, entities: list[dict]):
    if not entities:
        return

    with get_session() as session:
        session.query(GraphEntity).filter(GraphEntity.doc_id == doc_id).delete()
        for ent in entities:
            session.add(GraphEntity(
                doc_id=doc_id,
                entity_name=ent["name"],
                entity_type=ent["type"],
            ))

    try:
        driver = get_neo4j_driver()
        with driver.session() as neo_session:
            for ent in entities:
                result = neo_session.run(
                    "MERGE (e:Entity {name: $name}) SET e.type = $type RETURN elementId(e) AS node_id",
                    name=ent["name"], type=ent["type"],
                )
                record = result.single()
                if record:
                    ent["neo4j_node_id"] = record["node_id"]
            for ent in entities:
                neo_session.run(
                    "MATCH (e:Entity {name: $name}) "
                    "MERGE (d:Document {doc_id: $doc_id}) "
                    "MERGE (e)-[:APPEARS_IN]->(d)",
                    name=ent["name"], doc_id=doc_id,
                )
            if len(entities) > 1:
                names = [e["name"] for e in entities]
                neo_session.run(
                    "UNWIND $names AS n1 UNWIND $names AS n2 "
                    "WITH n1, n2 WHERE n1 < n2 "
                    "MATCH (a:Entity {name: n1}), (b:Entity {name: n2}) "
                    "MERGE (a)-[:CO_OCCURS]->(b)",
                    names=names,
                )
        driver.close()
    except Exception as e:
        logger.warning("Neo4j storage failed (non-fatal): %s", e)

    logger.info("Stored %d entities for doc_id=%d", len(entities), doc_id)
