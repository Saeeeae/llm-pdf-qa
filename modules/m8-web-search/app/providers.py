from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

import httpx

from .models import ProviderInfo, SearchRequest, SearchResult
from .policy import is_url_allowed


class ProviderError(RuntimeError):
    pass


class SearchProvider:
    name = "base"
    external = False

    def configured(self) -> bool:
        return True

    async def search(self, req: SearchRequest, safe_query: str) -> list[SearchResult]:
        raise NotImplementedError


def _filter_results(results: list[SearchResult], domains: list[str]) -> list[SearchResult]:
    filtered: list[SearchResult] = []
    for result in results:
        allowed, _ = is_url_allowed(result.url, domains)
        if allowed:
            filtered.append(result)
    return filtered


class CuratedBioProvider(SearchProvider):
    name = "curated"
    external = False

    async def search(self, req: SearchRequest, safe_query: str) -> list[SearchResult]:
        q = quote_plus(safe_query)
        now = datetime.now(timezone.utc)
        results = [
            SearchResult(
                title=f"PubMed search: {safe_query}",
                url=f"https://pubmed.ncbi.nlm.nih.gov/?term={q}",
                snippet="NCBI PubMed literature search entrypoint for the sanitized public query.",
                source="pubmed",
                fetched_at=now,
            ),
            SearchResult(
                title=f"ClinicalTrials.gov search: {safe_query}",
                url=f"https://clinicaltrials.gov/search?term={q}",
                snippet="ClinicalTrials.gov public trial registry search entrypoint.",
                source="clinicaltrials.gov",
                fetched_at=now,
            ),
            SearchResult(
                title=f"openFDA search: {safe_query}",
                url="https://open.fda.gov/apis/",
                snippet="openFDA public API index for drug, device, food, and safety datasets.",
                source="openfda",
                fetched_at=now,
            ),
            SearchResult(
                title=f"Europe PMC search: {safe_query}",
                url=f"https://europepmc.org/search?query={q}",
                snippet="Europe PMC publication and preprint search entrypoint.",
                source="europepmc",
                fetched_at=now,
            ),
        ]
        return _filter_results(results, req.domains)[: req.max_results]


class MockProvider(SearchProvider):
    name = "mock"
    external = False

    async def search(self, req: SearchRequest, safe_query: str) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Mock web result for {safe_query}",
                url="https://example.org/mock-result",
                snippet="Mock result generated inside M8; no external provider was called.",
                source="mock",
                fetched_at=datetime.now(timezone.utc),
            )
        ][: req.max_results]


class BraveProvider(SearchProvider):
    name = "brave"
    external = True

    def configured(self) -> bool:
        return bool(os.getenv("BRAVE_SEARCH_API_KEY"))

    async def search(self, req: SearchRequest, safe_query: str) -> list[SearchResult]:
        key = os.getenv("BRAVE_SEARCH_API_KEY")
        if not key:
            raise ProviderError("BRAVE_SEARCH_API_KEY is not configured")
        params: dict[str, str | int] = {
            "q": safe_query,
            "count": min(req.max_results, 20),
            "search_lang": req.locale.split("-")[0] if req.locale else "ko",
        }
        if req.freshness:
            params["freshness"] = req.freshness
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params=params,
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        raw_results = data.get("web", {}).get("results", [])
        results = [
            SearchResult(
                title=item.get("title") or item.get("url") or "Untitled",
                url=item.get("url", ""),
                snippet=item.get("description") or item.get("snippet") or "",
                source="brave",
                fetched_at=datetime.now(timezone.utc),
            )
            for item in raw_results
            if item.get("url")
        ]
        return _filter_results(results, req.domains)[: req.max_results]


class ExaProvider(SearchProvider):
    name = "exa"
    external = True

    def configured(self) -> bool:
        return bool(os.getenv("EXA_API_KEY"))

    async def search(self, req: SearchRequest, safe_query: str) -> list[SearchResult]:
        key = os.getenv("EXA_API_KEY")
        if not key:
            raise ProviderError("EXA_API_KEY is not configured")
        payload = {
            "query": safe_query,
            "numResults": req.max_results,
            "type": "auto",
        }
        if req.domains:
            payload["includeDomains"] = req.domains
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                json=payload,
                headers={"x-api-key": key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        raw_results = data.get("results", [])
        results = [
            SearchResult(
                title=item.get("title") or item.get("url") or "Untitled",
                url=item.get("url", ""),
                snippet=item.get("text") or item.get("summary") or "",
                source="exa",
                fetched_at=datetime.now(timezone.utc),
            )
            for item in raw_results
            if item.get("url")
        ]
        return _filter_results(results, req.domains)[: req.max_results]


class SearxngProvider(SearchProvider):
    name = "searxng"
    external = True

    def configured(self) -> bool:
        return bool(os.getenv("SEARXNG_URL"))

    async def search(self, req: SearchRequest, safe_query: str) -> list[SearchResult]:
        base = os.getenv("SEARXNG_URL", "").rstrip("/")
        if not base:
            raise ProviderError("SEARXNG_URL is not configured")
        params = {
            "q": safe_query,
            "format": "json",
            "language": req.locale,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{base}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        raw_results = data.get("results", [])
        results = [
            SearchResult(
                title=item.get("title") or item.get("url") or "Untitled",
                url=item.get("url", ""),
                snippet=item.get("content") or "",
                source="searxng",
                fetched_at=datetime.now(timezone.utc),
            )
            for item in raw_results
            if item.get("url")
        ]
        return _filter_results(results, req.domains)[: req.max_results]


_PROVIDERS: dict[str, SearchProvider] = {
    "curated": CuratedBioProvider(),
    "mock": MockProvider(),
    "brave": BraveProvider(),
    "exa": ExaProvider(),
    "searxng": SearxngProvider(),
}


def default_provider_name() -> str:
    return os.getenv("M8_DEFAULT_PROVIDER", "curated")


def get_provider(name: Optional[str]) -> SearchProvider:
    provider_name = name or default_provider_name()
    provider = _PROVIDERS.get(provider_name)
    if not provider:
        raise ProviderError(f"Unknown provider: {provider_name}")
    return provider


def provider_infos() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            name=p.name,
            configured=p.configured(),
            external=p.external,
            notes=(
                "offline deterministic provider"
                if not p.external
                else "external provider; only sanitized safe_query is sent"
            ),
        )
        for p in _PROVIDERS.values()
    ]
