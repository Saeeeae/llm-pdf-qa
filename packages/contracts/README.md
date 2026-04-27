# packages/contracts — OpenAPI SSOT

Each YAML file is the single source of truth for one backend module's HTTP API.
Downstream consumers (client SDKs, mock servers, validators) are generated from these specs.

## Files

| File | Module | Port |
|------|--------|------|
| m1-identity.openapi.yaml | M1 Identity / Auth | 8101 |
| m2-ingest.openapi.yaml | M2 Doc-to-MD Ingest | 8102 |
| m3-chunk-embed.openapi.yaml | M3 Chunk/Embed | 8103 |
| m4-rag.openapi.yaml | M4 RAG Engine | 8104 |
| m5-gateway.openapi.yaml | M5 API Gateway | 8080 |
| m7-admin.openapi.yaml | M7 Admin Backend | 8107 |
| m8-web-search.openapi.yaml | M8 Guarded Web Search | 8108 |

## Regenerate types

```bash
make contracts
```

This runs `openapi-generator-cli` for each spec, outputting TypeScript types to `packages/contracts/generated/`.
