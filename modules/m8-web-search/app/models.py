from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


ProviderName = Literal["curated", "brave", "exa", "searxng", "mock"]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    provider: Optional[ProviderName] = None
    locale: str = "ko-KR"
    freshness: Optional[str] = None
    domains: list[str] = Field(default_factory=list)
    max_results: int = Field(default=5, ge=1, le=20)


class SearchDecision(BaseModel):
    allowed: bool
    redacted_query: str
    query_hash: str
    blocked_reason: Optional[str] = None
    matched_signals: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    source: str
    published_at: Optional[str] = None
    fetched_at: Optional[datetime] = None


class Citation(BaseModel):
    title: str
    url: str
    source: str
    snippet: str = ""


class SearchResponse(BaseModel):
    provider: str
    safe_query: str
    query_hash: str
    blocked: bool = False
    blocked_reason: Optional[str] = None
    results: list[SearchResult] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    audit_id: str


class FetchRequest(BaseModel):
    url: HttpUrl
    max_chars: int = Field(default=6000, ge=500, le=50000)


class FetchResponse(BaseModel):
    url: str
    allowed: bool
    blocked_reason: Optional[str] = None
    title: Optional[str] = None
    text: str = ""
    fetched_at: Optional[datetime] = None


class ProviderInfo(BaseModel):
    name: str
    configured: bool
    external: bool
    notes: str
