import logging
from neo4j import GraphDatabase
from shared.config import shared_settings

logger = logging.getLogger(__name__)


def get_graph_context(query: str, max_hops: int = 2) -> str:
    keywords = [w.strip() for w in query.split() if len(w.strip()) > 1]
    if not keywords:
        return ""
    try:
        driver = GraphDatabase.driver(
            shared_settings.neo4j_url,
            auth=(shared_settings.neo4j_user, shared_settings.neo4j_password),
        )
        context_parts = []
        with driver.session() as session:
            for keyword in keywords[:5]:
                result = session.run(
                    "MATCH (e:Entity) WHERE e.name CONTAINS $kw "
                    "OPTIONAL MATCH (e)-[r*1..2]-(neighbor:Entity) "
                    "RETURN e.name AS entity, e.type AS type, "
                    "collect(DISTINCT neighbor.name)[..10] AS neighbors "
                    "LIMIT 5",
                    kw=keyword,
                )
                for record in result:
                    neighbors = record["neighbors"]
                    if neighbors:
                        context_parts.append(
                            f"{record['entity']} ({record['type']}): related to {', '.join(neighbors)}"
                        )
        driver.close()
        if context_parts:
            return "=== Graph Context ===\n" + "\n".join(context_parts) + "\n=== End Graph ==="
        return ""
    except Exception as e:
        logger.warning("Graph retrieval failed (non-fatal): %s", e)
        return ""
