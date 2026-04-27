"use client";
export const dynamic = "force-dynamic";

import { useQuery } from "@tanstack/react-query";
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts";
import { adminApi } from "../../lib/api";

// Placeholder time-series builders (real data would come from backend)
function last24hPoints() {
  return Array.from({ length: 24 }, (_, i) => ({
    hour: `${i}:00`,
    "queries/min": Math.round(Math.random() * 40 + 10),
  }));
}

function last7dPoints() {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  return days.map((d) => ({ day: d, "avg_latency_ms": Math.round(Math.random() * 80 + 20) }));
}

function last1hCpuRam() {
  return Array.from({ length: 12 }, (_, i) => ({
    min: `${i * 5}m`,
    cpu_pct: Math.round(Math.random() * 30 + 10),
    ram_pct: Math.round(Math.random() * 20 + 40),
  }));
}

const GAUGE_COLORS = ["#3b82f6", "#e5e7eb"];

function GpuGauge({ utilization }: { utilization: number }) {
  const data = [
    { name: "Used", value: utilization },
    { name: "Free", value: 100 - utilization },
  ];
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-2">GPU Utilization</h3>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="80%"
            startAngle={180}
            endAngle={0}
            innerRadius={60}
            outerRadius={80}
            dataKey="value"
          >
            {data.map((_, idx) => (
              <Cell key={idx} fill={GAUGE_COLORS[idx]} />
            ))}
          </Pie>
          <Tooltip formatter={(v, n) => [`${v}%`, n]} />
        </PieChart>
      </ResponsiveContainer>
      <p className="text-center text-2xl font-bold text-gray-900 -mt-6">{utilization}%</p>
    </div>
  );
}

export default function MetricsPage() {
  const gpu = useQuery({
    queryKey: ["metrics-gpu"],
    queryFn: adminApi.metricsGpu,
    refetchInterval: 10_000,
  });

  const gpuUtil = gpu.data?.utilization_pct ?? 0;
  const qpm = last24hPoints();
  const latency = last7dPoints();
  const cpuRam = last1hCpuRam();

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Metrics</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Queries per minute — last 24h */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Queries per Minute (Last 24h)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={qpm}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="queries/min"
                stroke="#3b82f6"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Avg chunk embedding latency — last 7d */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            Avg Chunk Embedding Latency (Last 7 Days)
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={latency}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="day" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit="ms" />
              <Tooltip />
              <Legend />
              <Bar dataKey="avg_latency_ms" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* GPU gauge */}
        <GpuGauge utilization={typeof gpuUtil === "number" ? Math.round(gpuUtil) : 0} />

        {/* CPU + RAM stacked area — last 1h */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">CPU &amp; RAM Usage (Last 1h)</h3>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={cpuRam}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="min" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit="%" domain={[0, 100]} />
              <Tooltip />
              <Legend />
              <Area
                type="monotone"
                dataKey="cpu_pct"
                stackId="1"
                stroke="#f59e0b"
                fill="#fef3c7"
                name="CPU %"
              />
              <Area
                type="monotone"
                dataKey="ram_pct"
                stackId="1"
                stroke="#10b981"
                fill="#d1fae5"
                name="RAM %"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
