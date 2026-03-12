import logging
import time

import httpx

from rag_serving.config import serving_settings
from shared.db import get_session
from shared.event_logger import get_event_logger
from shared.models.orm import WebSearchLog

logger = logging.getLogger(__name__)
elog = get_event_logger("serving")

GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"


async def search_web(
    query: str,
    num_results: int = 5,
    user_id: int | None = None,
    session_id: int | None = None,
) -> list[dict]:
    """Search the web using Google Custom Search JSON API.

    Returns a list of {title, url, snippet} dicts.
    Logs the request to web_search_log and event_log.
    Returns an empty list on any failure.
    """
    if not serving_settings.web_search_enabled:
        elog.info("Web search disabled by config", user_id=user_id, session_id=session_id)
        _log_to_db(
            query=query,
            user_id=user_id,
            session_id=session_id,
            was_blocked=True,
            block_reason="web_search_enabled=False",
            results_count=0,
        )
        return []

    if not serving_settings.google_api_key or not serving_settings.google_cx:
        elog.warning(
            "Web search skipped: google_api_key or google_cx not configured",
            user_id=user_id,
            session_id=session_id,
        )
        _log_to_db(
            query=query,
            user_id=user_id,
            session_id=session_id,
            was_blocked=True,
            block_reason="google_api_key or google_cx not set",
            results_count=0,
        )
        return []

    start = time.perf_counter()
    try:
        params = {
            "key": serving_settings.google_api_key,
            "cx": serving_settings.google_cx,
            "q": query,
            "num": min(num_results, 10),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(GOOGLE_CSE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        items = data.get("items", [])
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in items
        ]

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        elog.info(
            "Web search complete",
            user_id=user_id,
            session_id=session_id,
            duration_ms=elapsed_ms,
            details={"query": query[:200], "results_count": len(results)},
        )
        _log_to_db(
            query=query,
            user_id=user_id,
            session_id=session_id,
            was_blocked=False,
            results_count=len(results),
        )
        return results

    except httpx.HTTPStatusError as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        elog.error(
            "Web search HTTP error",
            user_id=user_id,
            session_id=session_id,
            duration_ms=elapsed_ms,
            error=e,
            details={"query": query[:200], "status_code": e.response.status_code},
        )
        _log_to_db(
            query=query,
            user_id=user_id,
            session_id=session_id,
            was_blocked=True,
            block_reason=f"HTTP {e.response.status_code}: {str(e)[:200]}",
            results_count=0,
        )
        return []

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        elog.error(
            "Web search failed",
            user_id=user_id,
            session_id=session_id,
            duration_ms=elapsed_ms,
            error=e,
            details={"query": query[:200]},
        )
        _log_to_db(
            query=query,
            user_id=user_id,
            session_id=session_id,
            was_blocked=True,
            block_reason=str(e)[:500],
            results_count=0,
        )
        return []


def _log_to_db(
    query: str,
    user_id: int | None,
    session_id: int | None,
    was_blocked: bool,
    results_count: int,
    block_reason: str | None = None,
) -> None:
    """Best-effort write to web_search_log table. Never raises."""
    try:
        with get_session() as db_session:
            db_session.add(WebSearchLog(
                user_id=user_id,
                session_id=session_id,
                query=query,
                was_blocked=was_blocked,
                block_reason=block_reason,
                results_count=results_count,
            ))
    except Exception:
        logger.debug("Failed to write web_search_log", exc_info=True)
