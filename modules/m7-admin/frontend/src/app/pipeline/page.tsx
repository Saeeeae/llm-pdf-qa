"use client";
export const dynamic = "force-dynamic";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";

interface PipelineRun {
  id: string;
  created_at: string;
  doc_count?: string | number;
  duration_s?: string | number;
  failures?: string | number;
  status?: string;
}

export default function PipelinePage() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: () => adminApi.pipelineRuns(50),
  });

  const trigger = useMutation({
    mutationFn: () =>
      fetch(
        `${process.env.NEXT_PUBLIC_ADMIN_API_BASE ?? "http://localhost:8080"}/api/v1/admin/pipeline/trigger`,
        { method: "POST" },
      ).then((r) => {
        if (!r.ok) throw new Error(`Failed: ${r.status}`);
        return r.json();
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline-runs"] }),
    onError: (e) => alert(`Trigger failed: ${e}`),
  });

  const runs = (data?.runs ?? []) as PipelineRun[];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Pipeline Runs</h1>
        <button
          onClick={() => trigger.mutate()}
          disabled={trigger.isPending}
          className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {trigger.isPending ? "Triggering…" : "Re-trigger"}
        </button>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}
      {error && <p className="text-sm text-red-500">Error: {String(error)}</p>}

      <div className="space-y-3">
        {runs.map((run, i) => (
          <div
            key={run.id ?? i}
            className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4"
          >
            <div
              className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                run.status === "success"
                  ? "bg-green-500"
                  : run.status === "failed"
                    ? "bg-red-500"
                    : "bg-gray-400"
              }`}
            />
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-900">
                {new Date(run.created_at).toLocaleString()}
              </p>
              <p className="text-xs text-gray-500">
                {run.doc_count ?? "?"} docs · {run.duration_s ?? "?"}s
                {run.failures && Number(run.failures) > 0 && (
                  <span className="ml-2 text-red-500">{run.failures} failures</span>
                )}
              </p>
            </div>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                run.status === "success"
                  ? "bg-green-100 text-green-700"
                  : run.status === "failed"
                    ? "bg-red-100 text-red-700"
                    : "bg-gray-100 text-gray-600"
              }`}
            >
              {run.status ?? "unknown"}
            </span>
          </div>
        ))}

        {!isLoading && runs.length === 0 && (
          <p className="text-sm text-gray-400">No pipeline runs recorded.</p>
        )}
      </div>
    </div>
  );
}
