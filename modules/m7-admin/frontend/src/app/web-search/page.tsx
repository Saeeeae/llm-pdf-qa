"use client";
export const dynamic = "force-dynamic";

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";

interface ProviderRow {
  name: string;
  configured: boolean;
  external: boolean;
  notes?: string;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-semibold text-gray-900 mt-1">{value}</p>
    </div>
  );
}

export default function WebSearchPage() {
  const providers = useQuery({
    queryKey: ["web-search-providers"],
    queryFn: adminApi.webSearchProviders,
    refetchInterval: 30_000,
  });
  const audit = useQuery({
    queryKey: ["web-search-audit"],
    queryFn: adminApi.webSearchAuditSummary,
    refetchInterval: 30_000,
  });
  const policy = useQuery({
    queryKey: ["web-search-policy"],
    queryFn: adminApi.webSearchPolicy,
    staleTime: 60_000,
  });

  const providerRows = (providers.data?.providers ?? []) as ProviderRow[];
  const providerCounts = audit.data?.providers ?? {};
  const policyRows: Array<[string, string | number]> = [
    ["Egress Boundary", String(policy.data?.egress_boundary ?? "m8-web-search")],
    [
      "Allowed Domains",
      (policy.data?.allowed_domains as string[] | undefined)?.join(", ") || "not restricted",
    ],
    ["Denied Domains", (policy.data?.denied_domains as string[] | undefined)?.join(", ") || "none"],
    ["Default Provider", String(policy.data?.default_provider ?? "curated")],
    ["Estimated Cost", `$${Number(audit.data?.estimated_cost_usd ?? 0).toFixed(2)}`],
    ["Cache Hits", audit.data?.cache_hits ?? 0],
    [
      "Confidential Terms",
      policy.data?.confidential_terms_configured ? "configured" : "not configured",
    ],
  ];

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Web Search</h1>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Stat label="External Queries" value={audit.data?.total ?? 0} />
        <Stat label="Allowed" value={audit.data?.allowed ?? 0} />
        <Stat label="Blocked" value={audit.data?.blocked ?? 0} />
        <Stat label="Failure Rate" value={`${Math.round(Number(audit.data?.failure_rate ?? 0) * 100)}%`} />
      </div>

      {(providers.data?.error || audit.data?.error) && (
        <p className="text-sm text-red-500 mb-4">
          {String(providers.data?.error ?? audit.data?.error)}
        </p>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-medium text-gray-800">Providers</h2>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                {["Name", "Configured", "External", "Calls"].map((h) => (
                  <th key={h} className="text-left px-4 py-2 text-xs font-medium text-gray-500 uppercase">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {providerRows.map((p) => (
                <tr key={p.name}>
                  <td className="px-4 py-3 text-gray-900">{p.name}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${p.configured ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"}`}>
                      {p.configured ? "yes" : "no"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{p.external ? "yes" : "no"}</td>
                  <td className="px-4 py-3 text-gray-600">{providerCounts[p.name] ?? 0}</td>
                </tr>
              ))}
              {!providers.isLoading && providerRows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-gray-400">
                    No provider data.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h2 className="text-sm font-medium text-gray-800 mb-3">Policy</h2>
          <dl className="text-sm divide-y divide-gray-100">
            {policyRows.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 py-2">
                <dt className="text-gray-500">{label}</dt>
                <dd className="text-gray-900 text-right">{String(value ?? "—")}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}
