import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


def env_first(*keys: str, default: str | None = None) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return default


def default_base_url() -> str:
    explicit = env_first("RAG_API_BASE_URL", "NEXT_PUBLIC_API_URL")
    if explicit:
        return explicit
    port = env_first("NEXT_PUBLIC_API_PORT", "SERVING_API_PORT", default="8002")
    return f"http://localhost:{port}"


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


class ApiError(RuntimeError):
    pass


@dataclass
class ApiResponse:
    status: int
    headers: dict[str, str]
    text: str
    data: Any


def request_json(
    *,
    base_url: str,
    method: str,
    path: str,
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 30.0,
    expected_statuses: tuple[int, ...] = (200,),
) -> ApiResponse:
    body = None
    headers = {"Accept": "application/json"}
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(
        f"{normalize_base_url(base_url)}{path}",
        data=body,
        headers=headers,
        method=method.upper(),
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else None
            result = ApiResponse(
                status=resp.getcode(),
                headers=dict(resp.headers.items()),
                text=raw,
                data=data,
            )
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        data = None
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None
        result = ApiResponse(
            status=exc.code,
            headers=dict(exc.headers.items()),
            text=raw,
            data=data,
        )
    except error.URLError as exc:
        raise ApiError(f"Request failed for {path}: {exc}") from exc

    if expected_statuses and result.status not in expected_statuses:
        detail = result.data if result.data is not None else result.text
        raise ApiError(f"{method.upper()} {path} returned {result.status}: {detail}")
    return result


def request_stream_probe(
    *,
    base_url: str,
    path: str,
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60.0,
    max_lines: int = 8,
    max_bytes: int = 4096,
) -> dict[str, Any]:
    body = None
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
    }
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(
        f"{normalize_base_url(base_url)}{path}",
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            lines: list[str] = []
            total = 0
            while len(lines) < max_lines and total < max_bytes:
                line = resp.readline()
                if not line:
                    break
                total += len(line)
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    lines.append(decoded)
                if decoded == "data: [DONE]":
                    break
            return {
                "status": resp.getcode(),
                "content_type": resp.headers.get("Content-Type", ""),
                "lines": lines,
            }
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ApiError(f"POST {path} returned {exc.code}: {raw}") from exc
    except error.URLError as exc:
        raise ApiError(f"Stream probe failed for {path}: {exc}") from exc


def login_and_get_token(
    *,
    base_url: str,
    email: str,
    password: str,
    timeout: float = 30.0,
) -> tuple[str, dict[str, Any]]:
    response = request_json(
        base_url=base_url,
        method="POST",
        path="/api/v1/auth/login",
        json_body={"email": email, "password": password},
        timeout=timeout,
        expected_statuses=(200,),
    )
    payload = response.data or {}
    token = payload.get("access_token")
    if not token:
        raise ApiError("Login succeeded but access_token was missing")
    return token, payload
