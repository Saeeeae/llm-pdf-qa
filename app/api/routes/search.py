import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db.models import AuditLog, User, WebSearchLog
from app.db.postgres import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_DENY_PATTERNS = [
    r"\b\d{3}-\d{4}-\d{4}\b",   # Korean phone numbers
    r"\b\d{6}-\d{7}\b",          # Korean SSN pattern
]


class WebSearchRequest(BaseModel):
    query: str
    session_id: int | None = None
    max_results: int = 5


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    results: list[WebSearchResult]
    query: str
    blocked: bool = False
    block_reason: str | None = None


def is_query_blocked(query: str) -> tuple[bool, str | None]:
    for pattern in DEFAULT_DENY_PATTERNS:
        if re.search(pattern, query):
            return True, f"Query contains restricted pattern"
    return False, None


@router.post("/web", response_model=WebSearchResponse)
def web_search(req: WebSearchRequest, user: User = Depends(get_current_user)):
    if not settings.web_search_enabled:
        raise HTTPException(status_code=503, detail="Web search is disabled")

    blocked, block_reason = is_query_blocked(req.query)

    with get_session() as session:
        log = WebSearchLog(
            user_id=user.user_id,
            session_id=req.session_id,
            query=req.query,
            was_blocked=blocked,
            block_reason=block_reason,
        )
        session.add(log)
        session.add(AuditLog(
            user_id=user.user_id,
            action_type="web_search",
            description=f"query={req.query[:100]}",
        ))

    if blocked:
        return WebSearchResponse(query=req.query, results=[], blocked=True, block_reason=block_reason)

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{settings.searxng_url}/search",
                params={"q": req.query, "format": "json", "language": "ko", "categories": "general"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as e:
        logger.error("SearXNG error: %s", e)
        raise HTTPException(status_code=503, detail="Search service unavailable")

    results = [
        WebSearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content", "")[:300],
        )
        for r in data.get("results", [])[:req.max_results]
    ]

    return WebSearchResponse(query=req.query, results=results)
