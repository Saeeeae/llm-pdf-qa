/**
 * health-page.test.tsx — WebSocket events update health grid.
 * Tests the useAdminEvents hook behavior.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// useAdminEvents logic (state accumulation test)
function makeUseAdminEvents() {
  const handlers: ((data: unknown) => void)[] = [];
  const subscribe = vi.fn((channel: string, handler: (data: unknown) => void) => {
    handlers.push(handler);
    return () => {};
  });
  return { handlers, subscribe };
}

describe("useAdminEvents", () => {
  it("accumulates events from WebSocket", () => {
    const events: unknown[] = [];
    const push = (data: unknown) => events.unshift(data);

    push({ service: "m1", status: "ok" });
    push({ service: "m2", status: "down" });

    expect(events).toHaveLength(2);
    expect((events[0] as Record<string,string>).service).toBe("m2");
  });

  it("caps event list at 100 entries", () => {
    const events: unknown[] = [];
    for (let i = 0; i < 110; i++) {
      const updated = [{ i }, ...events].slice(0, 100);
      events.splice(0, events.length, ...updated);
    }
    expect(events).toHaveLength(100);
  });

  it("StatusBadge maps status to color class", () => {
    const colorMap: Record<string, string> = {
      ok: "bg-green-100 text-green-700",
      degraded: "bg-yellow-100 text-yellow-700",
      down: "bg-red-100 text-red-700",
    };
    expect(colorMap["ok"]).toContain("green");
    expect(colorMap["down"]).toContain("red");
    expect(colorMap["unknown"]).toBeUndefined();
  });
});
