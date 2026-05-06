# M8 Web Search

On-prem guarded web search service. M8 is the only module intended to have internet egress.
All other modules should call web search through `M4 -> M8` or, for admin tooling, through `M5 -> M8`.

- **Port (host)**: 8108 → 8000 (container)
- **Build**: `make build` &nbsp;·&nbsp; **Run**: `make run` &nbsp;·&nbsp; **Test**: `make test` &nbsp;·&nbsp; **Logs**: `make log`
- **Default provider**: `curated` (offline deterministic bio-source citations)
- **Optional providers**: `brave`, `exa`, `searxng`, `mock`

## Safety model

M8 never sends raw internal context to a search provider. The search endpoint first applies DLP checks,
hashes the original query for audit, and only calls a provider when the query is public-safe.

Blocked by default:

- email addresses, phone-like identifiers, and Korean resident-registration-like identifiers
- local and mounted file paths such as `/data/...`
- internal project/code patterns such as `PROJECT ABC`, `EXP-123`, `ABC-1234`
- terms listed in `M8_CONFIDENTIAL_TERMS`

## API

```bash
curl -X POST http://localhost:8108/web-search/search \
  -H "Content-Type: application/json" \
  -d '{"query":"p53 phase 2 clinical trial","provider":"curated","max_results":3}'
```

## CLI inside the container

The previous module Makefile wrapped these as local-pytest entrypoints. With the docker-only Makefile, run them via `docker compose run`:

```bash
docker compose run --rm m8-web-search python -m app.cli search \
  --query "p53 phase 2 clinical trial" --provider curated
docker compose run --rm m8-web-search python -m app.cli crawl-curated
docker compose run --rm m8-web-search python -m app.cli crawl-allowlist \
  --domains nih.gov,fda.gov
```

## Provider notes

- `curated`: safe offline source pointers for PubMed, ClinicalTrials.gov, openFDA, and Europe PMC.
- `brave`: uses Brave Search API with `BRAVE_SEARCH_API_KEY`.
- `exa`: uses Exa Search API with `EXA_API_KEY`.
- `searxng`: uses a self-hosted SearXNG instance via `SEARXNG_URL`.
