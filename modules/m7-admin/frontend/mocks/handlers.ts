import { http, HttpResponse } from "msw";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8107";

export const handlers = [
  http.get(`${BASE}/admin/health`, () =>
    HttpResponse.json({ services: [{ name: "m1-identity", status: "ok" }] })
  ),
  http.get(`${BASE}/admin/audit-log`, () =>
    HttpResponse.json({ entries: [], total: 0 })
  ),
  http.get(`${BASE}/admin/metrics`, () =>
    HttpResponse.json({ queries_total: 0, queries_last_24h: 0, avg_latency_ms: 0 })
  ),
  http.get(`${BASE}/admin/web-search/providers`, () =>
    HttpResponse.json({
      providers: [
        { name: "curated", configured: true, external: false },
        { name: "brave", configured: false, external: true },
      ],
    })
  ),
  http.get(`${BASE}/admin/web-search/audit-summary`, () =>
    HttpResponse.json({
      total: 0,
      allowed: 0,
      blocked: 0,
      failed: 0,
      cache_hits: 0,
      external: 0,
      failure_rate: 0,
      estimated_cost_usd: 0,
      providers: {},
      recent: [],
    })
  ),
  http.get(`${BASE}/admin/web-search/policy`, () =>
    HttpResponse.json({
      default_provider: "curated",
      allowed_domains: [],
      denied_domains: [],
      confidential_terms_configured: false,
      egress_boundary: "m8-web-search",
    })
  ),
];
