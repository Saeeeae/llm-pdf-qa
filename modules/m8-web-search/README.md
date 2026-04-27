# M8 Web Search

On-prem guarded web search service. M8 is the only module intended to have internet egress.
All other modules should call web search through `M4 -> M8` or, for admin tooling, through `M5 -> M8`.

- **Port**: 8108
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

## Make targets

```bash
make search-once Q="p53 phase 2 clinical trial" PROVIDER=curated
make crawl-curated
make crawl-allowlist DOMAINS=nih.gov,fda.gov
make dlp-test
make eval-web
make cache-prune
```

## Provider notes

- `curated`: safe offline source pointers for PubMed, ClinicalTrials.gov, openFDA, and Europe PMC.
- `brave`: uses Brave Search API with `BRAVE_SEARCH_API_KEY`.
- `exa`: uses Exa Search API with `EXA_API_KEY`.
- `searxng`: uses a self-hosted SearXNG instance via `SEARXNG_URL`.
