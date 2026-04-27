/**
 * chat-stream.test.tsx — SSE token append + abort behavior.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock auth
vi.mock("../src/lib/auth", () => ({
  getAccessToken: () => "mock-token",
  silentRefresh: vi.fn().mockResolvedValue(true),
}));

function makeSSEStream(tokens: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream({
    pull(controller) {
      if (i >= tokens.length) {
        controller.close();
        return;
      }
      const sse = `event: token\ndata: ${JSON.stringify({ token: tokens[i++] })}\n\n`;
      controller.enqueue(encoder.encode(sse));
    },
  });
}

function makeSourcesStream(sources: object[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let done = false;
  return new ReadableStream({
    pull(controller) {
      if (done) { controller.close(); return; }
      done = true;
      const sse = `event: sources\ndata: ${JSON.stringify(sources)}\n\n`;
      controller.enqueue(encoder.encode(sse));
    },
  });
}

describe("streamChat SSE parsing", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("appends tokens in order", async () => {
    const tokens = ["Hello", " ", "world", "!"];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: makeSSEStream(tokens),
    });

    const { streamChat } = await import("../src/lib/sse");
    const received: string[] = [];
    const controller = new AbortController();
    await streamChat("hi", "sess-1", (t) => received.push(t), vi.fn(), controller.signal);
    expect(received).toEqual(tokens);
  });

  it("parses sources event", async () => {
    const sources = [{ title: "Doc A", chunk_id: "c1" }];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: makeSourcesStream(sources),
    });

    const { streamChat } = await import("../src/lib/sse");
    let receivedSources: object[] = [];
    await streamChat("q", "s", vi.fn(), (s) => { receivedSources = s; }, new AbortController().signal);
    expect(receivedSources).toEqual(sources);
  });

  it("throws AbortError when controller is aborted", async () => {
    const controller = new AbortController();
    global.fetch = vi.fn().mockImplementation(() =>
      new Promise((_, reject) => {
        controller.signal.addEventListener("abort", () => {
          const err = new DOMException("Aborted", "AbortError");
          reject(err);
        });
      }),
    );

    const { streamChat } = await import("../src/lib/sse");
    const p = streamChat("q", "s", vi.fn(), vi.fn(), controller.signal);
    controller.abort();
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
  });
});
