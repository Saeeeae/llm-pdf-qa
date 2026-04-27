# M6 UI — RAG Chat Frontend

Next.js 14 (app router) chat interface. Port **3000**.

## Purpose

End-user chat UI that streams responses from M5 Gateway (`/api/v1/chat` SSE).
Handles auth via httpOnly refresh cookie + in-memory access token.

## Dev

```bash
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

## Production build

```bash
npm run build      # outputs .next/standalone for Docker
```
Dockerfile: multi-stage (deps → build → slim runner). Image runs `node server.js`.

## Testing

No jest/playwright configured. Use MSW handlers for browser-based integration testing.
Key paths: `/login`, `/chat` (SSE streaming), `/` (auto-redirects based on session).
