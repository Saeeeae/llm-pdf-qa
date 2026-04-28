import asyncio
import os
import time
from enum import Enum
from typing import Optional
import httpx

# Connection pool shared across requests
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
            timeout=httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=5.0),
        )
    return _client


# --- Simple 3-state circuit breaker ---
class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, fail_threshold: int = 5, recovery_timeout: float = 30.0):
        self.state = State.CLOSED
        self.failures = 0
        self.fail_threshold = fail_threshold
        self.recovery_timeout = recovery_timeout
        self._opened_at: float = 0.0

    def record_success(self):
        self.failures = 0
        self.state = State.CLOSED

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.fail_threshold:
            self.state = State.OPEN
            self._opened_at = time.monotonic()

    def allow_request(self) -> bool:
        if self.state == State.CLOSED:
            return True
        if self.state == State.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self.state = State.HALF_OPEN
                return True
            return False
        # HALF_OPEN: allow one probe
        return True


# Per-target circuit breakers
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(target: str) -> CircuitBreaker:
    if target not in _breakers:
        _breakers[target] = CircuitBreaker()
    return _breakers[target]


async def proxy_request(
    request,
    target_url: str,
    target_name: str,
    timeout: Optional[httpx.Timeout] = None,
) -> httpx.Response:
    """Forward a Starlette request to a downstream service."""
    from mocks.fallback_responses import get_fallback

    breaker = get_breaker(target_name)
    if not breaker.allow_request():
        if os.getenv("DOWNSTREAM_FALLBACK") == "mock":
            return get_fallback(target_name)
        raise httpx.HTTPStatusError(
            "Circuit open",
            request=None,
            response=httpx.Response(503),
        )

    client = get_client()
    if timeout is None:
        timeout = httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=5.0)

    body = await request.body()
    # Strip hop-by-hop headers but PRESERVE Authorization — internal services
    # (m1, m4, m7, m8) decode the JWT to identify the caller. Stripping it
    # would make every downstream `get_current_user` 401.
    _STRIP = {"host", "content-length"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _STRIP}
    downstream_auth_token = os.getenv("DOWNSTREAM_SERVICE_TOKEN")
    if downstream_auth_token:
        headers["X-Service-Token"] = downstream_auth_token

    try:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=dict(request.query_params),
            timeout=timeout,
        )
        breaker.record_success()
        return resp
    except Exception:
        breaker.record_failure()
        if os.getenv("DOWNSTREAM_FALLBACK") == "mock":
            return get_fallback(target_name)
        raise
