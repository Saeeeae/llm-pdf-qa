import atexit
import logging
from threading import Lock

from neo4j import GraphDatabase
from shared.config import shared_settings
from shared.db import get_session
from shared.search_terms import extract_candidate_terms, expand_terms, get_alias_rows

logger = logging.getLogger(__name__)

_driver = None
_driver_lock = Lock()


def _close_driver() -> None:
    global _driver
    if _driver is None:
        return
    try:
        _driver.close()
    finally:
        _driver = None


atexit.register(_close_driver)


def _get_driver():
    global _driver
    if _driver is None:
        with _driver_lock:
            if _driver is None:
                _driver = GraphDatabase.driver(
                    shared_settings.neo4j_url,
                    auth=(shared_settings.neo4j_user, shared_settings.neo4j_password),
                )
    return _driver


def get_graph_context(query: str, max_hops: int = 2) -> str:
    with get_session() as db_session:
        alias_rows = get_alias_rows(db_session)

    keywords = list(dict.fromkeys(expand_terms(extract_candidate_terms(query) + [query], alias_rows)))[:8]
    if not keywords:
        return ""

    hop_span = max(1, min(max_hops, 2))
    entity_limit = 8
    neighbor_limit = 10

    try:
        driver = _get_driver()
        context_parts = []
        with driver.session() as session:
            query_result = session.run(
                f"""
                MATCH (e:Entity)
                WHERE any(kw IN $keywords WHERE e.name CONTAINS kw)
                WITH DISTINCT e
                LIMIT $entity_limit
                OPTIONAL MATCH (e)-[r]-(neighbor:Entity)
                WHERE neighbor <> e
                WITH e, neighbor, coalesce(r.weight, 0) AS w
                ORDER BY w DESC
                WITH e, collect(DISTINCT neighbor.name)[..{neighbor_limit}] AS neighbors
                RETURN e.name AS entity,
                       e.type AS type,
                       neighbors
                LIMIT $entity_limit
                """,
                keywords=keywords[:5],
                entity_limit=entity_limit,
            )
            for record in query_result:
                neighbors = [name for name in record["neighbors"] if name][:neighbor_limit]
                if neighbors:
                    context_parts.append(
                        f"{record['entity']} ({record['type']}): related to {', '.join(neighbors)}"
                    )

        if context_parts:
            return "=== Graph Context ===\n" + "\n".join(context_parts) + "\n=== End Graph ==="
        return ""
    except Exception as e:
        logger.warning("Graph retrieval failed (non-fatal): %s", e)
        return ""
