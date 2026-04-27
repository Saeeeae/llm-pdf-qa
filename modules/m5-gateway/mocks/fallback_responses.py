import httpx

_FALLBACKS = {
    "m1": {"status": "fallback", "service": "m1-identity"},
    "m2": {"status": "fallback", "service": "m2-ingest"},
    "m3": {"status": "fallback", "service": "m3-chunk-embed"},
    "m4": {"status": "fallback", "service": "m4-rag"},
    "m7": {"status": "fallback", "service": "m7-admin"},
    "m8": {"provider": "fallback", "blocked": True, "blocked_reason": "m8_unavailable", "results": [], "citations": []},
}


def get_fallback(target: str) -> httpx.Response:
    import json
    payload = _FALLBACKS.get(target, {"status": "fallback", "service": target})
    return httpx.Response(200, json=payload)
