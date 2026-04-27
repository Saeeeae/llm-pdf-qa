from __future__ import annotations

import argparse
import asyncio
import json

from .cache import clear_cache
from .models import SearchRequest
from .routers.search import search


async def _search(args) -> None:
    req = SearchRequest(query=args.query, provider=args.provider, max_results=args.max_results)
    result = await search(req)
    print(result.model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="m8-web-search")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search")
    s.add_argument("--query", required=True)
    s.add_argument("--provider", default="curated")
    s.add_argument("--max-results", type=int, default=5)

    sub.add_parser("crawl-curated")
    allow = sub.add_parser("crawl-allowlist")
    allow.add_argument("--domains", default="")
    sub.add_parser("cache-prune")

    args = parser.parse_args()
    if args.cmd == "search":
        asyncio.run(_search(args))
    elif args.cmd == "crawl-curated":
        print(json.dumps({"status": "ok", "message": "curated crawl entrypoint ready"}))
    elif args.cmd == "crawl-allowlist":
        domains = [d.strip() for d in args.domains.split(",") if d.strip()]
        print(json.dumps({"status": "ok", "domains": domains}))
    elif args.cmd == "cache-prune":
        print(json.dumps({"status": "ok", "cleared": clear_cache()}))


if __name__ == "__main__":
    main()
