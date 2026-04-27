"use client";
export const dynamic = "force-dynamic";

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";

export default function DocumentsPage() {
  const metrics = useQuery({
    queryKey: ["metrics-embedding"],
    queryFn: adminApi.metricsEmbedding,
    staleTime: 30_000,
  });

  const chunking = useQuery({
    queryKey: ["metrics-chunking"],
    queryFn: adminApi.metricsChunking,
    staleTime: 30_000,
  });

  const data = metrics.data ?? {};
  const chunkData = chunking.data ?? {};

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Documents</h1>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Total Docs", value: (data as Record<string,unknown>).total_docs ?? "—" },
          { label: "Chunks/Doc Avg", value: (data as Record<string,unknown>).chunks_per_doc_avg ?? "—" },
          { label: "Avg Embed Latency", value: (data as Record<string,unknown>).avg_latency_ms ? `${(data as Record<string,unknown>).avg_latency_ms} ms` : "—" },
          { label: "Last Embed Run", value: (data as Record<string,unknown>).last_embedding_run ? String((data as Record<string,unknown>).last_embedding_run).slice(0, 10) : "—" },
        ].map(({ label, value }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{String(value)}</p>
          </div>
        ))}
      </div>

      {(metrics.error || chunking.error) && (
        <p className="text-sm text-red-500">
          Error fetching metrics: {String(metrics.error ?? chunking.error)}
        </p>
      )}
    </div>
  );
}
