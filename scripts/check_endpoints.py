#!/usr/bin/env python3
import argparse
from typing import Any

from _api_utils import (
    ApiError,
    default_base_url,
    env_first,
    login_and_get_token,
    request_json,
    request_stream_probe,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-check auth/chat/admin endpoints")
    parser.add_argument("--base-url", default=default_base_url())
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--user-token", default=env_first("RAG_USER_TOKEN"))
    parser.add_argument("--user-email", default=env_first("RAG_USER_EMAIL"))
    parser.add_argument("--user-password", default=env_first("RAG_USER_PASSWORD"))
    parser.add_argument("--admin-token", default=env_first("RAG_ADMIN_TOKEN"))
    parser.add_argument("--admin-email", default=env_first("RAG_ADMIN_EMAIL"))
    parser.add_argument("--admin-password", default=env_first("RAG_ADMIN_PASSWORD"))
    parser.add_argument("--chat-message", default="Phase 3 endpoint smoke test 질문입니다.")
    parser.add_argument("--debug-query", default="최신 표 찾아줘")
    parser.add_argument("--skip-stream", action="store_true")
    return parser.parse_args()


def record(results: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    results.append({"name": name, "ok": ok, "detail": detail})


def ensure_token(base_url: str, timeout: float, token: str | None, email: str | None, password: str | None) -> tuple[str | None, dict[str, Any] | None]:
    if token:
        return token, None
    if email and password:
        access_token, payload = login_and_get_token(
            base_url=base_url,
            email=email,
            password=password,
            timeout=timeout,
        )
        return access_token, payload
    return None, None


def main() -> int:
    args = parse_args()
    results: list[dict[str, Any]] = []

    try:
        health = request_json(
            base_url=args.base_url,
            method="GET",
            path="/health",
            timeout=args.timeout,
            expected_statuses=(200,),
        )
        record(results, "GET /health", True, str(health.data))
    except ApiError as exc:
        record(results, "GET /health", False, str(exc))
        return 1

    user_token, _ = ensure_token(args.base_url, args.timeout, args.user_token, args.user_email, args.user_password)
    admin_token, _ = ensure_token(args.base_url, args.timeout, args.admin_token, args.admin_email, args.admin_password)

    if user_token:
        try:
            me = request_json(
                base_url=args.base_url,
                method="GET",
                path="/api/v1/auth/me",
                token=user_token,
                timeout=args.timeout,
                expected_statuses=(200,),
            )
            record(results, "GET /api/v1/auth/me", True, f"user_id={me.data.get('user_id')}")

            created = request_json(
                base_url=args.base_url,
                method="POST",
                path="/api/v1/chat/sessions",
                token=user_token,
                json_body={},
                timeout=args.timeout,
                expected_statuses=(200,),
            )
            session_id = created.data["session_id"]
            record(results, "POST /api/v1/chat/sessions", True, f"session_id={session_id}")

            listed = request_json(
                base_url=args.base_url,
                method="GET",
                path="/api/v1/chat/sessions",
                token=user_token,
                timeout=args.timeout,
                expected_statuses=(200,),
            )
            record(results, "GET /api/v1/chat/sessions", True, f"count={len(listed.data or [])}")

            messages = request_json(
                base_url=args.base_url,
                method="GET",
                path=f"/api/v1/chat/sessions/{session_id}/messages",
                token=user_token,
                timeout=args.timeout,
                expected_statuses=(200,),
            )
            record(results, "GET /api/v1/chat/sessions/{id}/messages", True, f"count={len(messages.data or [])}")

            if args.skip_stream:
                record(results, "POST /api/v1/chat/sessions/{id}/stream", True, "skipped")
            else:
                stream = request_stream_probe(
                    base_url=args.base_url,
                    path=f"/api/v1/chat/sessions/{session_id}/stream",
                    token=user_token,
                    json_body={"message": args.chat_message, "search_scope": "all", "use_web_search": False},
                    timeout=args.timeout,
                )
                ok = stream["status"] == 200 and "text/event-stream" in stream["content_type"]
                detail = f"content_type={stream['content_type']} lines={stream['lines'][:3]}"
                record(results, "POST /api/v1/chat/sessions/{id}/stream", ok, detail)

            request_json(
                base_url=args.base_url,
                method="DELETE",
                path=f"/api/v1/chat/sessions/{session_id}",
                token=user_token,
                timeout=args.timeout,
                expected_statuses=(204,),
            )
            record(results, "DELETE /api/v1/chat/sessions/{id}", True, "204 No Content")
        except ApiError as exc:
            record(results, "User Endpoint Flow", False, str(exc))
    else:
        record(results, "User Endpoint Flow", True, "skipped: no user credentials or token")

    if admin_token:
        admin_checks = [
            ("GET /api/v1/admin/system-summary", "GET", "/api/v1/admin/system-summary", None),
            ("GET /api/v1/admin/documents", "GET", "/api/v1/admin/documents?limit=5", None),
            ("GET /api/v1/admin/pipeline-logs", "GET", "/api/v1/admin/pipeline-logs?limit=5", None),
            ("GET /api/v1/admin/queries", "GET", "/api/v1/admin/queries?limit=5", None),
            (
                "POST /api/v1/admin/queries/debug",
                "POST",
                "/api/v1/admin/queries/debug",
                {
                    "query": args.debug_query,
                    "search_scope": "all",
                    "retrieve_k": 12,
                    "rerank_k": 5,
                },
            ),
        ]

        for name, method, path, payload in admin_checks:
            try:
                response = request_json(
                    base_url=args.base_url,
                    method=method,
                    path=path,
                    token=admin_token,
                    json_body=payload,
                    timeout=args.timeout,
                    expected_statuses=(200,),
                )
                detail = "ok"
                if isinstance(response.data, list):
                    detail = f"count={len(response.data)}"
                elif isinstance(response.data, dict):
                    detail = ",".join(sorted(list(response.data.keys()))[:6])
                record(results, name, True, detail)
            except ApiError as exc:
                record(results, name, False, str(exc))
    else:
        record(results, "Admin Endpoint Flow", True, "skipped: no admin credentials or token")

    print("Endpoint Smoke Check")
    failed = [item for item in results if not item["ok"]]
    for item in results:
        status = "PASS" if item["ok"] else "FAIL"
        print(f"[{status}] {item['name']} :: {item['detail']}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
