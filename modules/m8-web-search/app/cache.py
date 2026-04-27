from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheEntry:
    expires_at: float
    value: Any


_CACHE: dict[str, CacheEntry] = {}


def ttl_seconds() -> int:
    return int(os.getenv("M8_CACHE_TTL_SECONDS", "900"))


def get_cache(key: str) -> Optional[Any]:
    entry = _CACHE.get(key)
    if not entry:
        return None
    if entry.expires_at < time.time():
        _CACHE.pop(key, None)
        return None
    return entry.value


def set_cache(key: str, value: Any) -> None:
    _CACHE[key] = CacheEntry(expires_at=time.time() + ttl_seconds(), value=value)


def clear_cache() -> int:
    n = len(_CACHE)
    _CACHE.clear()
    return n
