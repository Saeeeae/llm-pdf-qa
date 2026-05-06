# packages/contracts — OpenAPI SSOT

Each YAML file is the single source of truth for one backend module's HTTP API.
Downstream consumers (client SDKs, mock servers, validators) are generated from these specs.

## Files

| File | Module | Host port |
|------|--------|-----------|
| m1-identity.openapi.yaml | M1 Identity / Auth | 8101 |
| m2-ingest.openapi.yaml | M2 Doc-to-MD Ingest | 8102 |
| m3-chunk-embed.openapi.yaml | M3 Chunk/Embed | 8103 |
| m4-rag.openapi.yaml | M4 RAG Engine | 8104 |
| m5-gateway.openapi.yaml | M5 API Gateway | 8080 |
| m7-admin.openapi.yaml | M7 Admin Backend | 8107 |
| m8-web-search.openapi.yaml | M8 Guarded Web Search | 8108 |

## Lock files

Each spec has a paired `.sha256` lock. CI verifies module implementations match the locked spec. To update locks after intentional spec changes:

```bash
bash scripts/contracts-lock.sh
bash scripts/contracts-verify.sh
```

## Regenerate types

```bash
# YAML syntax validation (lightweight)
for f in packages/contracts/*.yaml; do
  python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK $f"
done

# Full lint (requires redocly)
for f in packages/contracts/*.yaml; do redocly lint "$f" --format=stylish; done
```

> Note: previous Make targets `make contracts*` (root) and `make contracts`
> (this dir) were retired in the docker-only Makefile refactor. Run the
> scripts above directly. CI still enforces drift via the `contracts-verify`
> step in `.github/workflows/ci.yml`.
