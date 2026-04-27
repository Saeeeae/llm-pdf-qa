"use client";
export const dynamic = "force-dynamic";

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";
import { useAdminEvents } from "../../lib/ws";

interface ServiceStatus {
  name: string;
  status: "ok" | "degraded" | "down" | string;
  checked_at: string;
  error?: string;
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    ok: "bg-green-100 text-green-700",
    degraded: "bg-yellow-100 text-yellow-700",
    down: "bg-red-100 text-red-700",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colorMap[status] ?? "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}

export default function HealthPage() {
  // 5 s polling fallback — WebSocket is preferred but degrades gracefully
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ["health-aggregate"],
    queryFn: adminApi.healthAggregate,
    refetchInterval: 5_000,
  });

  // Real-time overlay from WebSocket
  const wsEvents = useAdminEvents<{ service: string; status: string }>("pipeline_events");

  const services = (data?.services ?? []) as ServiceStatus[];

  // Merge WS overrides (latest per service name)
  const wsOverride: Record<string, string> = {};
  for (const e of wsEvents) {
    if (e.service) wsOverride[e.service] = e.status;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">System Health</h1>
        {dataUpdatedAt > 0 && (
          <p className="text-xs text-gray-400">
            Last polled: {new Date(dataUpdatedAt).toLocaleTimeString()}
          </p>
        )}
      </div>

      {isLoading && <p className="text-sm text-gray-400">Checking services…</p>}
      {error && <p className="text-sm text-red-500">Error: {String(error)}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {services.map((s) => {
          const liveStatus = wsOverride[s.name] ?? s.status;
          return (
            <div
              key={s.name}
              title={s.error ? `Error: ${s.error}` : `Last check: ${s.checked_at}`}
              className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4"
            >
              <div
                className={`w-3 h-3 rounded-full flex-shrink-0 ${
                  liveStatus === "ok"
                    ? "bg-green-500"
                    : liveStatus === "degraded"
                      ? "bg-yellow-400"
                      : "bg-red-500"
                }`}
                aria-label={`${s.name} status: ${liveStatus}`}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900">{s.name}</p>
                <p className="text-xs text-gray-400 truncate">
                  {s.error ?? new Date(s.checked_at).toLocaleTimeString()}
                </p>
              </div>
              <StatusBadge status={liveStatus} />
            </div>
          );
        })}

        {!isLoading && services.length === 0 && (
          <p className="text-sm text-gray-400 col-span-3">No service data available.</p>
        )}
      </div>
    </div>
  );
}
