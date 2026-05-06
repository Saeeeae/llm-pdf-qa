# M7 Admin Frontend

Next.js 14 admin dashboard. Port **3001**. Requires `admin.read` permission.

> Frontend modules (m6, m7-admin/frontend) are currently **npm-based** —
> they do not have a `docker-compose.module.yml` yet. The standard
> docker-only `make build/run/...` flow used by m1-m5/m8 does not apply
> here. A future task will containerize the FE; until then, run via npm
> directly (or the production multi-stage Dockerfile).

## Purpose

Admin UI for the RAG-LLM service. All API calls go through M5 Gateway at
`NEXT_PUBLIC_ADMIN_API_BASE` → `/api/v1/admin/*` → M7 backend.

## Dev (local npm)

```bash
cd modules/m7-admin/frontend
npm install
npm run dev        # http://localhost:3001
```

## Env vars

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_ADMIN_API_BASE` | `http://localhost:8080` | M5 Gateway URL |
| `NEXT_PUBLIC_M6_URL` | `http://localhost:3000` | M6 UI URL for auth redirect |

## Pages & permissions

| Page | Path | Permission |
|---|---|---|
| Dashboard | `/` | `admin.read` |
| Users | `/users` | `admin.read` |
| Audit Log | `/audit-log` | `audit.read` |
| Metrics | `/metrics` | `admin.read` |
| Health | `/health` | `admin.read` |
| Pipeline Runs | `/pipeline` | `admin.read` |

All pages use `force-dynamic` (no edge caching).

## Production build (Docker, run manually)

```bash
docker build -t rag-m7-admin-fe:local -f modules/m7-admin/frontend/Dockerfile modules/m7-admin/frontend
docker run -p 3001:3001 rag-m7-admin-fe:local
```

## Notes

Auth uses same httpOnly refresh cookie pattern as M6 UI.
Unauthenticated or unauthorized users are redirected to the M6 login page.
