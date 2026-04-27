# M7 Admin Frontend

Next.js 14 admin dashboard. Port **3001**. Requires `admin.read` permission.

## Purpose

Admin UI for the RAG-LLM service. All API calls go through M5 Gateway at
`NEXT_PUBLIC_ADMIN_API_BASE` → `/api/v1/admin/*` → M7 backend.

## Dev

```bash
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

## Production build

```bash
npm run build
```
Dockerfile: multi-stage, slim runner image. Runs `node server.js` on port 3001.

## Notes

Auth uses same httpOnly refresh cookie pattern as M6 UI.
Unauthenticated or unauthorized users are redirected to the M6 login page.
