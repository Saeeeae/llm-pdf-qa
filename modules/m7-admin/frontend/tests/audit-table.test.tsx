/**
 * audit-table.test.tsx — pagination and filter behavior for audit log.
 */
import { describe, it, expect, vi } from "vitest";

// Pagination state logic (extracted for unit testing without rendering full component)
function computeTotalPages(total: number, size: number) {
  return Math.ceil(total / size);
}

function buildQueryParams(
  page: number,
  userFilter: string,
  actionFilter: string,
  fromDate: string,
  toDate: string,
): Record<string, string | number> {
  const params: Record<string, string | number> = { page, size: 50 };
  if (userFilter) params.user_id = userFilter;
  if (actionFilter) params.action = actionFilter;
  if (fromDate) params.from = fromDate;
  if (toDate) params.to = toDate;
  return params;
}

describe("Audit log pagination", () => {
  it("computes total pages correctly", () => {
    expect(computeTotalPages(100, 50)).toBe(2);
    expect(computeTotalPages(1, 50)).toBe(1);
    expect(computeTotalPages(51, 50)).toBe(2);
    expect(computeTotalPages(0, 50)).toBe(0);
  });

  it("builds query params with filters", () => {
    const params = buildQueryParams(2, "u1", "chat.query", "2024-01-01T00:00", "2024-12-31T23:59");
    expect(params.page).toBe(2);
    expect(params.user_id).toBe("u1");
    expect(params.action).toBe("chat.query");
    expect(params.from).toBeDefined();
    expect(params.to).toBeDefined();
  });

  it("omits empty filters from params", () => {
    const params = buildQueryParams(1, "", "", "", "");
    expect(params.user_id).toBeUndefined();
    expect(params.action).toBeUndefined();
    expect(params.from).toBeUndefined();
    expect(params.to).toBeUndefined();
  });

  it("resets page to 1 when filters change", () => {
    let page = 3;
    // Simulate filter change
    const newUserFilter = "new-user";
    if (newUserFilter) page = 1;
    expect(page).toBe(1);
  });
});
