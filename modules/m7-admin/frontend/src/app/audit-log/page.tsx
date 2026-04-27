"use client";
export const dynamic = "force-dynamic";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";
import { ExportButton } from "../../components/ExportButton";

interface AuditEntry {
  id: string;
  user_id: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  created_at: string;
}

export default function AuditLogPage() {
  const [page, setPage] = useState(1);
  const [userFilter, setUserFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const params: Record<string, string | number> = { page, size: 50 };
  if (userFilter) params.user_id = userFilter;
  if (actionFilter) params.action = actionFilter;
  if (fromDate) params.from = fromDate;
  if (toDate) params.to = toDate;

  const { data, isLoading, error } = useQuery({
    queryKey: ["audit-log", params],
    queryFn: () => adminApi.auditLog(params),
  });

  const entries = (data?.entries ?? []) as AuditEntry[];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 50);

  const exportParams: Record<string, string> = {};
  if (userFilter) exportParams.user_id = userFilter;
  if (actionFilter) exportParams.action = actionFilter;
  if (fromDate) exportParams.from = fromDate;
  if (toDate) exportParams.to = toDate;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Audit Log</h1>
        <div className="flex gap-2">
          <ExportButton
            path="/admin/export/audit-log.csv"
            params={{ ...exportParams, format: "csv" }}
            filename="audit-log.csv"
            label="Export CSV"
          />
          <ExportButton
            path="/admin/export/audit-log.csv"
            params={{ ...exportParams, format: "xlsx" }}
            filename="audit-log.xlsx"
            label="Export XLSX"
          />
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <input
          placeholder="User ID"
          value={userFilter}
          onChange={(e) => { setUserFilter(e.target.value); setPage(1); }}
          aria-label="Filter by user ID"
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          placeholder="Action (e.g. chat.query)"
          value={actionFilter}
          onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
          aria-label="Filter by action"
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-48"
        />
        <input
          type="datetime-local"
          value={fromDate}
          onChange={(e) => { setFromDate(e.target.value); setPage(1); }}
          aria-label="From date"
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          type="datetime-local"
          value={toDate}
          onChange={(e) => { setToDate(e.target.value); setPage(1); }}
          aria-label="To date"
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}
      {error && <p className="text-sm text-red-500">Error: {String(error)}</p>}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["Timestamp", "User", "Action", "Resource Type", "Resource ID"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">
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
                <td className="px-4 py-2 text-gray-900 font-mono text-xs">{e.user_id}</td>
                <td className="px-4 py-2">
                  <span className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-700">{e.action}</span>
                </td>
                <td className="px-4 py-2 text-gray-600 text-xs">{e.resource_type ?? "—"}</td>
                <td className="px-4 py-2 text-gray-600 font-mono text-xs">{e.resource_id ?? "—"}</td>
              </tr>
            ))}
            {!isLoading && entries.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-400 text-sm">
                  No entries found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center gap-2 mt-4 text-sm text-gray-600">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
          >
            Previous
          </button>
          <span>Page {page} of {totalPages} ({total} total)</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1 rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
