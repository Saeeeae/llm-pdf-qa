# M6 UI — RAG Chat Frontend

Next.js 14 (app router) chat interface. Port **3000**.

> Frontend modules (m6, m7-admin/frontend) are currently **npm-based** —
> they do not have a `docker-compose.module.yml` yet. The standard
> docker-only `make build/run/...` flow used by m1-m5/m8 does not apply
> here. A future task will containerize the FE; until then, run via npm
> directly (or via the production multi-stage Dockerfile shipped with
> the module).

## Purpose

End-user chat UI that streams responses from M5 Gateway (`/api/v1/chat` SSE).
Handles auth via httpOnly refresh cookie + in-memory access token.

## Dev (local npm)

```bash
cd modules/m6-ui
npm install
npm run dev        # http://localhost:3000
```

## Env vars

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8080` | M5 Gateway base URL |
| `NEXT_PUBLIC_USE_MOCKS` | — | Set to `1` to enable MSW mock mode |

## Mock mode

Set `NEXT_PUBLIC_USE_MOCKS=1` and the MSW service worker intercepts API calls.
Handlers are in `mocks/handlers.ts` (login, /me, chat streaming).

## Auth cookie requirement (for M1/M5 team)

Login response **must** include:
```
Set-Cookie: refresh_token=<token>; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth/refresh
```
The browser sends this cookie automatically on `POST /api/v1/auth/refresh`.

## Production build (Docker, run manually)

```bash
docker build -t rag-m6-ui:local -f modules/m6-ui/Dockerfile modules/m6-ui
docker run -p 3000:3000 rag-m6-ui:local
```
Multi-stage Dockerfile (deps → build → slim runner) outputs `node server.js` runtime.

## Testing

No jest/playwright configured. Use MSW handlers for browser-based integration testing.
Key paths: `/login`, `/chat` (SSE streaming), `/` (auto-redirects based on session).
