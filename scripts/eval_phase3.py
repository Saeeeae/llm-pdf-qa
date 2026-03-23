#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from _api_utils import ApiError, default_base_url, env_first, login_and_get_token, request_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Phase 3 retrieval quality via /api/v1/admin/queries/debug")
    parser.add_argument("--base-url", default=default_base_url())
    parser.add_argument("--token", default=env_first("RAG_ADMIN_TOKEN"))
    parser.add_argument("--email", default=env_first("RAG_ADMIN_EMAIL"))
    parser.add_argument("--password", default=env_first("RAG_ADMIN_PASSWORD"))
    parser.add_argument("--dataset", default="eval/phase3_queries.sample.jsonl")
    parser.add_argument("--debug-user-id", type=int, default=None)
    parser.add_argument("--default-search-scope", default="all")
    parser.add_argument("--default-retrieve-k", type=int, default=20)
    parser.add_argument("--default-rerank-k", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def load_cases(dataset_path: str) -> list[dict[str, Any]]:
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")

    cases: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        payload = json.loads(stripped)
        payload["_line_no"] = line_no
        cases.append(payload)
    if not cases:
        raise ValueError(f"No cases found in {path}")
    return cases


def lower_list(values: list[str] | None) -> list[str]:
    return [value.lower() for value in (values or []) if value]


def chunk_matches(case: dict[str, Any], chunk: dict[str, Any]) -> bool:
    checks: list[bool] = []
    match_mode = str(case.get("match_mode") or "all").lower()

    block_types = lower_list(case.get("expected_block_types"))
    if block_types:
        checks.append(str(chunk.get("block_type") or "").lower() in block_types)

    file_substrings = lower_list(case.get("expected_file_substrings"))
    if file_substrings:
        file_name = str(chunk.get("file_name") or "").lower()
        checks.append(any(term in file_name for term in file_substrings))

    text_substrings = lower_list(case.get("expected_text_substrings"))
    if text_substrings:
        haystack = " ".join(
            str(chunk.get(key) or "")
            for key in ("preview_text", "section_path", "file_name")
        ).lower()
        checks.append(any(term in haystack for term in text_substrings))

    section_substrings = lower_list(case.get("expected_section_substrings"))
    if section_substrings:
        section = str(chunk.get("section_path") or "").lower()
        checks.append(any(term in section for term in section_substrings))

    if not checks:
        return False
    if match_mode == "any":
        return any(checks)
    return all(checks)


def first_hit_rank(case: dict[str, Any], chunks: list[dict[str, Any]]) -> int | None:
    for index, chunk in enumerate(chunks, start=1):
        if chunk_matches(case, chunk):
            return index
    return None


def evaluate_case(base_url: str, token: str, timeout: float, defaults: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "query": case["query"],
        "search_scope": case.get("search_scope", defaults["search_scope"]),
        "debug_user_id": case.get("debug_user_id", defaults["debug_user_id"]),
        "retrieve_k": case.get("retrieve_k", defaults["retrieve_k"]),
        "rerank_k": case.get("rerank_k", defaults["rerank_k"]),
    }
    response = request_json(
        base_url=base_url,
        method="POST",
        path="/api/v1/admin/queries/debug",
        token=token,
        json_body=payload,
        timeout=timeout,
        expected_statuses=(200,),
    )
    data = response.data or {}
    retrieved_chunks = data.get("retrieved_chunks") or []
    reranked_chunks = data.get("reranked_chunks") or []

    retrieved_hit_rank = first_hit_rank(case, retrieved_chunks)
    reranked_hit_rank = first_hit_rank(case, reranked_chunks)
    expected_intent = case.get("expected_retrieval_intent")
    actual_intent = data.get("retrieval_intent")
    intent_match = expected_intent is None or expected_intent == actual_intent

    max_rank = int(case.get("max_reranked_hit_rank") or payload["rerank_k"])
    pass_result = intent_match and reranked_hit_rank is not None and reranked_hit_rank <= max_rank

    return {
        "line_no": case["_line_no"],
        "query": case["query"],
        "expected_retrieval_intent": expected_intent,
        "actual_retrieval_intent": actual_intent,
        "intent_match": intent_match,
        "retrieved_hit_rank": retrieved_hit_rank,
        "reranked_hit_rank": reranked_hit_rank,
        "pass": pass_result,
        "retrieve_k": payload["retrieve_k"],
        "rerank_k": payload["rerank_k"],
        "retrieved_count": len(retrieved_chunks),
        "reranked_count": len(reranked_chunks),
        "top_reranked_preview": [
            {
                "chunk_id": chunk.get("chunk_id"),
                "file_name": chunk.get("file_name"),
                "block_type": chunk.get("block_type"),
                "rerank_score": chunk.get("rerank_score"),
                "preview_text": chunk.get("preview_text"),
            }
            for chunk in reranked_chunks[:3]
        ],
    }


def print_summary(results: list[dict[str, Any]]) -> None:
    total = len(results)
    retrieved_hits = [item for item in results if item["retrieved_hit_rank"] is not None]
    reranked_hits = [item for item in results if item["reranked_hit_rank"] is not None]
    passed = [item for item in results if item["pass"]]
    intent_matches = [item for item in results if item["intent_match"]]

    print("Phase 3 Evaluation")
    print(f"cases={total}")
    print(f"retrieved_hit_rate={len(retrieved_hits)}/{total} ({(len(retrieved_hits) / total) * 100:.1f}%)")
    print(f"reranked_hit_rate={len(reranked_hits)}/{total} ({(len(reranked_hits) / total) * 100:.1f}%)")
    print(f"intent_match_rate={len(intent_matches)}/{total} ({(len(intent_matches) / total) * 100:.1f}%)")
    print(f"pass_rate={len(passed)}/{total} ({(len(passed) / total) * 100:.1f}%)")

    if reranked_hits:
        avg_rank = mean(item["reranked_hit_rank"] for item in reranked_hits if item["reranked_hit_rank"] is not None)
        print(f"avg_reranked_hit_rank={avg_rank:.2f}")

    print("")
    for item in results:
        status = "PASS" if item["pass"] else "FAIL"
        print(
            f"[{status}] line={item['line_no']} "
            f"intent={item['actual_retrieval_intent']} "
            f"retrieved_hit={item['retrieved_hit_rank']} "
            f"reranked_hit={item['reranked_hit_rank']} "
            f"query={item['query']}"
        )


def main() -> int:
    args = parse_args()
    cases = load_cases(args.dataset)

    token = args.token
    if not token:
        if not args.email or not args.password:
            raise SystemExit("Provide --token or both --email and --password")
        token, _ = login_and_get_token(
            base_url=args.base_url,
            email=args.email,
            password=args.password,
            timeout=args.timeout,
        )

    defaults = {
        "search_scope": args.default_search_scope,
        "debug_user_id": args.debug_user_id,
        "retrieve_k": args.default_retrieve_k,
        "rerank_k": args.default_rerank_k,
    }

    results: list[dict[str, Any]] = []
    for case in cases:
        try:
            result = evaluate_case(args.base_url, token, args.timeout, defaults, case)
            results.append(result)
        except ApiError as exc:
            failure = {
                "line_no": case["_line_no"],
                "query": case["query"],
                "pass": False,
                "error": str(exc),
                "intent_match": False,
                "retrieved_hit_rank": None,
                "reranked_hit_rank": None,
                "actual_retrieval_intent": None,
            }
            results.append(failure)
            if args.fail_fast:
                raise

    print_summary(results)

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps({"results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nSaved JSON report to {args.output_json}")

    return 0 if all(item["pass"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
