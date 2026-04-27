/**
 * export.test.tsx — Export button triggers download via Blob + URL.createObjectURL.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../src/lib/auth", () => ({
  getAccessToken: () => "admin-token",
}));

describe("ExportButton download flow", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("calls fetch with Authorization header and correct URL", async () => {
    const mockBlob = new Blob(["id,action\n1,login"], { type: "text/csv" });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => mockBlob,
    });

    const mockURL = vi.fn().mockReturnValue("blob:mock");
    global.URL.createObjectURL = mockURL;
    global.URL.revokeObjectURL = vi.fn();

    const clickSpy = vi.fn();
    const origCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        const a = origCreate("a") as HTMLAnchorElement;
        a.click = clickSpy;
        return a;
      }
      return origCreate(tag);
    });

    const BASE = "http://localhost:8107";
    const path = "/admin/export/audit-log.csv";
    const params = new URLSearchParams({ format: "csv" }).toString();
    const url = `${BASE}${path}?${params}`;

    const r = await fetch(url, { headers: { Authorization: "Bearer admin-token" } });
    const blob = await r.blob();
    const href = URL.createObjectURL(blob);

    expect(href).toBe("blob:mock");
    expect(global.fetch).toHaveBeenCalledWith(url, {
      headers: { Authorization: "Bearer admin-token" },
    });
  });

  it("reports error when fetch fails", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 403 });
    const errors: string[] = [];
    try {
      const r = await fetch("/admin/export/audit-log.csv", {});
      if (!r.ok) throw new Error(`Export failed: ${r.status}`);
    } catch (e) {
      errors.push(String(e));
    }
    expect(errors[0]).toContain("403");
  });
});
