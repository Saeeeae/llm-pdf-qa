"use client";
export const dynamic = "force-dynamic";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";

interface QueryLogEntry {
  id: string;
  user_id: string;
  email?: string;
  created_at: string;
  latency_ms?: string;
  status?: string;
  query?: string;
}

export default function QueryLogPage() {
  const [limit, setLimit] = useState(100);

  const { data, isLoading, error } = useQuery({
    queryKey: ["query-log", limit],
    queryFn: () => adminApi.logsQuery(limit),
    staleTime: 30_000,
  });

  const entries = (data?.entries ?? []) as QueryLogEntry[];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Query Log</h1>
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          aria-label="Number of entries"
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {[50, 100, 250, 500].map((n) => (
            <option key={n} value={n}>Last {n}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}
      {error && <p className="text-sm text-red-500">Error: {String(error)}</p>}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["Timestamp", "User", "Query", "Latency", "Status"].map((h) => (
                <th
                  key={h}
                  className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {entries.map((e) => (
              <tr key={e.id} className="hover:bg-gray-50">
                <td className="px-4 py-2 text-gray-500 whitespace-nowrap text-xs">
                  {new Date(e.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-gray-700 text-xs">{e.email ?? e.user_id}</td>
                <td className="px-4 py-2 text-gray-800 max-w-xs truncate" title={e.query ?? ""}>
                  {e.query ?? "—"}
                </td>
                <td className="px-4 py-2 text-gray-600 text-xs">
                  {e.latency_ms ? `${e.latency_ms} ms` : "—"}
                </td>
                <td className="px-4 py-2">
                  {e.status ? (
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        e.status === "ok"
                          ? "bg-green-100 text-green-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {e.status}
                    </span>
                  ) : "—"}
                </td>
              </tr>
            ))}
            {!isLoading && entries.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-400 text-sm">
                  No query log entries.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
