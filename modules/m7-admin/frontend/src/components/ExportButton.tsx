"use client";
/**
 * ExportButton — triggers a file download from the admin export endpoint.
 * Uses Blob + URL.createObjectURL to avoid opening a new tab.
 */
import { useState } from "react";
import { getAccessToken } from "../lib/auth";

const BASE = process.env.NEXT_PUBLIC_ADMIN_API_BASE ?? "http://localhost:8107";

interface Props {
  path: string; // e.g. /admin/export/audit-log.csv
  params?: Record<string, string>;
  filename?: string;
  label?: string;
}

export function ExportButton({ path, params = {}, filename = "export", label = "Export" }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);
    try {
      const q = new URLSearchParams(params).toString();
      const url = `${BASE}${path}${q ? "?" + q : ""}`;
      const token = getAccessToken();
      const r = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!r.ok) throw new Error(`Export failed: ${r.status}`);
      const blob = await r.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(href);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="inline-flex flex-col items-end gap-1">
      <button
        onClick={handleClick}
        disabled={loading}
        aria-label={label}
        className="text-sm text-blue-600 hover:text-blue-800 border border-blue-200 rounded-lg px-3 py-1.5 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {loading ? "Exporting…" : label}
      </button>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
