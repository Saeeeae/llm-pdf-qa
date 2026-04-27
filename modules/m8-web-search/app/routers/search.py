from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, status

from ..audit import read_summary, write_audit
from ..cache import get_cache, set_cache
from ..dlp import sanitize_query
from ..html_extract import extract_text
from ..models import Citation, FetchRequest, FetchResponse, SearchRequest, SearchResponse
from ..policy import is_url_allowed
from ..providers import ProviderError, default_provider_name, get_provider, provider_infos

router = APIRouter(prefix="/web-search", tags=["web-search"])


def _cache_key(provider: str, safe_query: str, req: SearchRequest) -> str:
    payload = {
        "provider": provider,
        "query": safe_query,
        "locale": req.locale,
        "freshness": req.freshness,
        "domains": sorted(req.domains),
        "max_results": req.max_results,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    decision = sanitize_query(req.query)
    provider_name = req.provider or default_provider_name()

    if not decision.allowed:
        audit_id = write_audit(
            {
                "action": "web_search.blocked",
                "provider": provider_name,
                "query_hash": decision.query_hash,
                "redacted_query": decision.redacted_query,
                "blocked": True,
                "blocked_reason": decision.blocked_reason,
                "matched_signals": decision.matched_signals,
            }
        )
        return SearchResponse(
            provider=provider_name,
            safe_query=decision.redacted_query,
            query_hash=decision.query_hash,
            blocked=True,
            blocked_reason=decision.blocked_reason,
            audit_id=audit_id,
        )

    try:
        provider = get_provider(req.provider)
    except ProviderError as exc:
        write_audit(
            {
                "action": "web_search.provider_error",
                "provider": provider_name,
                "query_hash": decision.query_hash,
                "redacted_query": decision.redacted_query,
                "blocked": False,
                "failed": True,
                "error": str(exc),
            }
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    key = _cache_key(provider.name, decision.redacted_query, req)
    cached = get_cache(key)
    if cached is not None:
        audit_id = write_audit(
            {
                "action": "web_search.cache_hit",
                "provider": provider.name,
                "query_hash": decision.query_hash,
                "redacted_query": decision.redacted_query,
                "blocked": False,
                "result_count": len(cached),
            }
        )
        citations = [Citation(**r.model_dump()) for r in cached]
        return SearchResponse(
            provider=provider.name,
            safe_query=decision.redacted_query,
            query_hash=decision.query_hash,
            results=cached,
            citations=citations,
            audit_id=audit_id,
        )

    try:
        results = await provider.search(req, decision.redacted_query)
    except ProviderError as exc:
        write_audit(
            {
                "action": "web_search.provider_error",
                "provider": provider.name,
                "query_hash": decision.query_hash,
                "redacted_query": decision.redacted_query,
                "blocked": False,
                "failed": True,
                "external": provider.external,
                "error": str(exc),
            }
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        write_audit(
            {
                "action": "web_search.provider_error",
                "provider": provider.name,
                "query_hash": decision.query_hash,
                "redacted_query": decision.redacted_query,
                "blocked": False,
                "failed": True,
                "external": provider.external,
                "error": type(exc).__name__,
            }
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    set_cache(key, results)
    audit_id = write_audit(
        {
            "action": "web_search.allowed",
            "provider": provider.name,
            "query_hash": decision.query_hash,
            "redacted_query": decision.redacted_query,
            "blocked": False,
            "external": provider.external,
            "result_count": len(results),
            "urls": [r.url for r in results],
        }
    )
    citations = [Citation(**r.model_dump()) for r in results]
    return SearchResponse(
        provider=provider.name,
        safe_query=decision.redacted_query,
        query_hash=decision.query_hash,
        results=results,
        citations=citations,
        audit_id=audit_id,
    )


@router.post("/fetch", response_model=FetchResponse)
async def fetch(req: FetchRequest):
    url = str(req.url)
    allowed, reason = is_url_allowed(url)
    if not allowed:
        write_audit(
            {
                "action": "web_fetch.blocked",
                "provider": "fetch",
                "query_hash": hashlib.sha256(url.encode()).hexdigest(),
                "blocked": True,
                "blocked_reason": reason,
                "url": url,
            }
        )
        return FetchResponse(url=url, allowed=False, blocked_reason=reason)

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "M8-Web-Search/0.1"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        return FetchResponse(url=url, allowed=False, blocked_reason="unsupported_content_type")

    title, text = extract_text(resp.text, req.max_chars)
    write_audit(
        {
            "action": "web_fetch.allowed",
            "provider": "fetch",
            "query_hash": hashlib.sha256(url.encode()).hexdigest(),
            "blocked": False,
            "url": url,
            "content_chars": len(text),
        }
    )
    return FetchResponse(
        url=url,
        allowed=True,
        title=title,
        text=text,
        fetched_at=datetime.now(timezone.utc),
    )


@router.get("/providers")
def providers():
    return {"providers": [p.model_dump() for p in provider_infos()]}


@router.get("/audit/summary")
def audit_summary():
    return read_summary()
