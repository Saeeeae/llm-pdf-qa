/**
 * MSW handlers for local development mock mode.
 * Enable via NEXT_PUBLIC_USE_MOCKS=1
 */
import { http, HttpResponse } from "msw";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";

// Simulate SSE stream for chat
function mockChatStream(message: string): ReadableStream<Uint8Array> {
  const tokens = `Mock response to: "${message}"`.split(" ");
  const encoder = new TextEncoder();
  let i = 0;

  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (i >= tokens.length) {
        controller.close();
        return;
      }
      const token = tokens[i++];
      const sse = `event: token\ndata: ${JSON.stringify({ token: token + " " })}\n\n`;
      controller.enqueue(encoder.encode(sse));
      // Simulate streaming delay
      await new Promise((r) => setTimeout(r, 80));
    },
  });
}

export const handlers = [
  http.post(`${BASE}/api/v1/auth/login`, async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    if (body.password === "wrong") {
      return HttpResponse.json({ detail: "Invalid credentials" }, { status: 401 });
    }
    return HttpResponse.json(
      { access_token: "mock.jwt.token" },
      {
        headers: {
          "Set-Cookie":
            "refresh_token=mock-refresh; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth/refresh",
        },
      },
    );
  }),

  http.post(`${BASE}/api/v1/auth/refresh`, () =>
    HttpResponse.json({ access_token: "mock.jwt.refreshed" }),
  ),

  http.get(`${BASE}/api/v1/me`, () =>
    HttpResponse.json({
      user_id: "mock-usr-001",
      email: "mock@example.com",
      name: "Mock User",
      role: "user",
      permissions: ["chat.query"],
    }),
  ),

  http.post(`${BASE}/api/v1/chat`, async ({ request }) => {
    const body = (await request.json()) as { message: string; session_id: string };
    return new Response(mockChatStream(body.message), {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  }),
];
