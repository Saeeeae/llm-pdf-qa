"use client";
export const dynamic = "force-dynamic";

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "../lib/api";

function StatCard({ label, value, unit = "" }: { label: string; value: string | number; unit?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-bold text-gray-900 mt-1">
        {value}
        {unit && <span className="text-base font-normal text-gray-500 ml-1">{unit}</span>}
      </p>
    </div>
  );
}

export default function DashboardPage() {
  const gpu = useQuery({
    queryKey: ["metrics-gpu"],
    queryFn: adminApi.metricsGpu,
    refetchInterval: 5000,
  });
  const server = useQuery({
    queryKey: ["metrics-server"],
    queryFn: adminApi.metricsServer,
    refetchInterval: 5000,
  });
  const pipeline = useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: () => adminApi.pipelineRuns(1),
    refetchInterval: 5000,
  });

  const gpuUtil = gpu.data?.utilization_pct ?? "—";
  const cpuPct = server.data?.cpu_pct ?? "—";
  const ramPct = server.data?.ram_pct ?? "—";
  const lastRun = (pipeline.data?.runs as Array<Record<string, unknown>>)?.[0]?.created_at ?? "—";

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Dashboard</h1>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="GPU Utilization" value={gpuUtil !== "—" ? `${gpuUtil}` : "—"} unit="%" />
        <StatCard label="CPU" value={cpuPct !== "—" ? `${cpuPct}` : "—"} unit="%" />
        <StatCard label="RAM" value={ramPct !== "—" ? `${ramPct}` : "—"} unit="%" />
        <StatCard
          label="Last Pipeline Run"
          value={typeof lastRun === "string" ? lastRun.slice(0, 10) : "—"}
        />
      </div>

      {gpu.error && (
        <p className="text-sm text-red-500 mt-4">GPU metrics unavailable: {String(gpu.error)}</p>
      )}
    </div>
  );
}
