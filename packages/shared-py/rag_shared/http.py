import httpx
from typing import Any


async def call_service(
    url: str,
    method: str = "GET",
    json: Any = None,
    timeout: float = 10.0,
) -> httpx.Response:
    """HTTP client with a simple circuit-breaker fallback hook."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, json=json)
            response.raise_for_status()
            return response
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        # Circuit-breaker hook: callers can catch this and return cached/default data.
        raise RuntimeError(f"Service unreachable: {url}") from exc
