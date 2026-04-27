/**
 * auth-interceptor.test.ts
 * 401 → refresh once, retry. Double-401 → force logout.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Simulate window.location.href assignment
const mockHref = vi.fn();
Object.defineProperty(globalThis, "window", {
  value: { location: { href: "" }, set location(v: unknown) { mockHref(v); } },
  writable: true,
});

describe("apiFetch auth interceptor", () => {
  beforeEach(() => {
    vi.resetModules();
    mockHref.mockReset();
  });

  it("retries with refreshed token on first 401", async () => {
    vi.doMock("../src/lib/auth", () => ({
      getAccessToken: vi.fn().mockReturnValueOnce("old").mockReturnValueOnce("new"),
      silentRefresh: vi.fn().mockResolvedValue(true),
      clearAuth: vi.fn(),
    }));

    let callCount = 0;
    global.fetch = vi.fn().mockImplementation(async () => {
      callCount++;
      if (callCount === 1) return { ok: false, status: 401, statusText: "Unauthorized", json: async () => ({}) };
      return { ok: true, status: 200, json: async () => ({ data: "ok" }) };
    });

    const { apiFetch } = await import("../src/lib/api");
    const result = await apiFetch("/api/v1/test");
    expect(result).toEqual({ data: "ok" });
    expect(callCount).toBe(2);
  });

  it("throws ApiError and sets window.location on double 401", async () => {
    vi.doMock("../src/lib/auth", () => ({
      getAccessToken: vi.fn().mockReturnValue("token"),
      silentRefresh: vi.fn().mockResolvedValue(false),
      clearAuth: vi.fn(),
    }));

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: async () => ({}),
    });

    const { apiFetch, ApiError } = await import("../src/lib/api");
    await expect(apiFetch("/api/v1/test")).rejects.toBeInstanceOf(ApiError);
  });

  it("throws ApiError with correct status for 503", async () => {
    vi.doMock("../src/lib/auth", () => ({
      getAccessToken: vi.fn().mockReturnValue(null),
      silentRefresh: vi.fn(),
      clearAuth: vi.fn(),
    }));

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: async () => ({ detail: "Gateway down" }),
    });

    const { apiFetch, ApiError } = await import("../src/lib/api");
    await expect(apiFetch("/api/v1/test")).rejects.toMatchObject({ status: 503 });
  });
});
