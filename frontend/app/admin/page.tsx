"use client";

import { startTransition, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Clock3,
  Database,
  FileText,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
  Waves,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";

interface DocStats {
  total: number;
  indexed: number;
  failed: number;
  pending: number;
}

interface UserItem {
  user_id: number;
  usr_name: string;
  email: string;
  role_name: string;
  dept_name: string;
  is_active: boolean;
  last_login: string | null;
}

interface PipelineFailure {
  id: number;
  doc_id: number | null;
  doc_file_name?: string | null;
  stage: string;
  error_message: string | null;
  started_at: string | null;
}

interface SyncRun {
  id: number;
  sync_type: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  files_added: number;
  files_modified: number;
  files_deleted: number;
}

interface SystemSummary {
  documents: DocStats;
  active_users_7d: number;
  queries_7d: number;
  recent_pipeline_failures: PipelineFailure[];
  recent_sync_runs: SyncRun[];
  pipeline_running_count: number;
  event_errors_24h: number;
}

interface PipelineLogItem {
  id: number;
  doc_id: number | null;
  doc_file_name?: string | null;
  stage: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  metadata?: Record<string, unknown> | null;
}

interface ModuleStatItem {
  module: string;
  total_events: number;
  errors: number;
  warnings: number;
  avg_duration_ms: number | null;
}

interface DocumentItem {
  doc_id: number;
  file_name: string;
  path: string;
  type: string;
  status: string;
  language: string | null;
  total_page_cnt: number;
  size: number | null;
  folder_name: string | null;
  dept_name: string | null;
  role_name: string | null;
  chunk_count: number;
  image_count: number;
  entity_count: number;
  error_msg: string | null;
  created_at: string;
  updated_at: string;
}

interface DocumentDetail extends DocumentItem {
  recent_pipeline_logs: PipelineLogItem[];
}

type AdminTab = "overview" | "documents" | "users" | "pipeline";
type PipelineFilter = "all" | "failed" | "running" | "success";
type DocumentFilter = "all" | "indexed" | "pending" | "failed";

const docCards: Array<{
  key: keyof DocStats;
  label: string;
  tone: string;
  surface: string;
  filter: DocumentFilter;
}> = [
  {
    key: "total",
    label: "전체 문서",
    tone: "text-slate-900",
    surface: "from-slate-100 to-white",
    filter: "all",
  },
  {
    key: "indexed",
    label: "인덱싱 완료",
    tone: "text-emerald-700",
    surface: "from-emerald-100 to-white",
    filter: "indexed",
  },
  {
    key: "pending",
    label: "대기/처리중",
    tone: "text-amber-700",
    surface: "from-amber-100 to-white",
    filter: "pending",
  },
  {
    key: "failed",
    label: "실패",
    tone: "text-rose-700",
    surface: "from-rose-100 to-white",
    filter: "failed",
  },
];

function fmtDate(value: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString("ko-KR");
}

function formatBytes(value: number | null) {
  if (!value || value <= 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 100 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`;
}

function statusPill(status: string | null) {
  if (!status) return "bg-slate-100 text-slate-500 border-slate-200";
  if (status === "success" || status === "indexed") return "bg-emerald-100 text-emerald-700 border-emerald-200";
  if (status === "failed") return "bg-rose-100 text-rose-700 border-rose-200";
  if (status === "running" || status === "processing") return "bg-sky-100 text-sky-700 border-sky-200";
  return "bg-amber-100 text-amber-700 border-amber-200";
}

function moduleTone(item: ModuleStatItem) {
  if (item.errors > 0) return "border-rose-200 bg-rose-50/80";
  if (item.warnings > 0) return "border-amber-200 bg-amber-50/80";
  return "border-emerald-200 bg-emerald-50/80";
}

function inferStageFromModule(module: string) {
  const normalized = module.toLowerCase();
  if (normalized.includes("graph")) return "graph_extract";
  if (normalized.includes("parse") || normalized.includes("mineru")) return "mineru_parse";
  if (normalized.includes("index") || normalized.includes("embed") || normalized.includes("chunk")) return "index";
  return "all";
}

function metricCard(
  label: string,
  value: number,
  hint: string,
  accent: string,
  icon: ReactNode,
  onClick?: () => void,
) {
  const Element = onClick ? "button" : "div";
  return (
    <Element
      onClick={onClick}
      className={`rounded-3xl border border-slate-200 bg-white p-5 text-left shadow-sm transition ${
        onClick ? "hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-200/60" : ""
      }`}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">{label}</p>
          <p className="mt-2 text-3xl font-semibold text-slate-950">{value}</p>
        </div>
        <div className={`rounded-2xl p-3 ${accent}`}>{icon}</div>
      </div>
      <p className="mt-3 text-sm text-slate-500">{hint}</p>
    </Element>
  );
}

export default function AdminPage() {
  const { user, fetchMe } = useAuthStore();
  const router = useRouter();
  const [summary, setSummary] = useState<SystemSummary | null>(null);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [pipelineLogs, setPipelineLogs] = useState<PipelineLogItem[]>([]);
  const [moduleStats, setModuleStats] = useState<ModuleStatItem[]>([]);
  const [activeTab, setActiveTab] = useState<AdminTab>("overview");
  const [pipelineFilter, setPipelineFilter] = useState<PipelineFilter>("all");
  const [pipelineStageFilter, setPipelineStageFilter] = useState("all");
  const [documentFilter, setDocumentFilter] = useState<DocumentFilter>("all");
  const [documentQuery, setDocumentQuery] = useState("");
  const [selectedDocument, setSelectedDocument] = useState<DocumentDetail | null>(null);
  const [selectedPipelineLog, setSelectedPipelineLog] = useState<PipelineLogItem | null>(null);
  const [isDocumentLoading, setIsDocumentLoading] = useState(false);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

  const loadDocumentDetail = async (docId: number) => {
    setIsDocumentLoading(true);
    try {
      const res = await api.get(`/api/v1/admin/documents/${docId}`);
      setSelectedDocument(res.data);
      setSelectedPipelineLog(null);
    } catch {
      setLoadError("문서 상세 정보를 불러오지 못했습니다.");
    } finally {
      setIsDocumentLoading(false);
    }
  };

  const loadAdminData = async (showBusy = false) => {
    if (showBusy) setIsRefreshing(true);
    setLoadError("");

    try {
      const [
        summaryRes,
        documentsRes,
        usersRes,
        pipelineRes,
        modulesRes,
        selectedDocumentRes,
      ] = await Promise.all([
        api.get("/api/v1/admin/system-summary"),
        api.get("/api/v1/admin/documents", { params: { limit: 80 } }),
        api.get("/api/v1/admin/users"),
        api.get("/api/v1/admin/pipeline-logs", { params: { limit: 40 } }),
        api.get("/api/v1/admin/stats/modules", { params: { days: 7 } }),
        selectedDocument
          ? api.get(`/api/v1/admin/documents/${selectedDocument.doc_id}`).catch(() => null)
          : Promise.resolve(null),
      ]);

      startTransition(() => {
        setSummary(summaryRes.data);
        setDocuments(documentsRes.data);
        setUsers(usersRes.data);
        setPipelineLogs(pipelineRes.data);
        setModuleStats(modulesRes.data);
        if (selectedDocumentRes?.data) {
          setSelectedDocument(selectedDocumentRes.data);
        }
        setLastUpdated(new Date().toISOString());
      });
    } catch {
      setLoadError("관리자 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      if (showBusy) setIsRefreshing(false);
    }
  };

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      let currentUser = user;
      if (!currentUser) {
        await fetchMe();
        currentUser = useAuthStore.getState().user;
      }

      if (cancelled) return;

      if (!currentUser) {
        router.push("/login");
        return;
      }
      if (currentUser.auth_level < 100) {
        router.push("/chat");
        return;
      }

      await loadAdminData(true);
      if (!cancelled) setIsBootstrapping(false);
    };

    bootstrap();

    return () => {
      cancelled = true;
    };
  }, [fetchMe, router, user]);

  useEffect(() => {
    if (isBootstrapping || !autoRefresh) return;
    const timer = window.setInterval(() => {
      loadAdminData(false);
    }, 30000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, isBootstrapping, selectedDocument]);

  const filteredDocuments = documents.filter((item) => {
    const matchesStatus = documentFilter === "all" ? true : item.status === documentFilter;
    const query = documentQuery.trim().toLowerCase();
    const matchesQuery =
      query.length === 0
        ? true
        : [item.file_name, item.path, item.type, item.dept_name, item.role_name, item.folder_name]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(query));
    return matchesStatus && matchesQuery;
  });

  const availableStages = ["all", ...Array.from(new Set(pipelineLogs.map((item) => item.stage).filter(Boolean)))];

  const filteredPipelineLogs = pipelineLogs.filter((item) => {
    const matchesStatus = pipelineFilter === "all" ? true : item.status === pipelineFilter;
    const matchesStage = pipelineStageFilter === "all" ? true : item.stage === pipelineStageFilter;
    return matchesStatus && matchesStage;
  });

  if (isBootstrapping) {
    return (
      <div className="min-h-screen bg-[radial-gradient(circle_at_top,_#e0f2fe,_#f8fafc_45%,_#ffffff)]">
        <div className="mx-auto flex min-h-screen max-w-7xl items-center justify-center p-6">
          <div className="rounded-3xl border border-slate-200 bg-white/90 px-8 py-7 text-center shadow-xl shadow-slate-200/70 backdrop-blur">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-100 text-sky-700">
              <RefreshCw className="h-5 w-5 animate-spin" />
            </div>
            <p className="text-sm font-medium text-slate-800">운영 콘솔을 준비하는 중입니다</p>
            <p className="mt-1 text-sm text-slate-500">권한과 시스템 상태를 확인하고 있어요.</p>
          </div>
        </div>
      </div>
    );
  }

  if (!user || user.auth_level < 100) return null;

  const failureCount = summary?.recent_pipeline_failures.length ?? 0;
  const healthScore = Math.max(
    25,
    100 -
      failureCount * 10 -
      (summary?.event_errors_24h ?? 0) * 5 -
      (summary?.documents.failed ?? 0) * 2,
  );
  const topUsers = users.slice(0, 5);

  const jumpToPipeline = (status: PipelineFilter, stage = "all") => {
    setActiveTab("pipeline");
    setPipelineFilter(status);
    setPipelineStageFilter(stage);
  };

  const openPipelineDetail = (item: PipelineLogItem) => {
    setSelectedDocument(null);
    setSelectedPipelineLog(item);
    setActiveTab("pipeline");
  };

  const openDocumentDetail = async (docId: number) => {
    setActiveTab("documents");
    await loadDocumentDetail(docId);
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_#dbeafe,_#eff6ff_18%,_#f8fafc_42%,_#f8fafc)] p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <section className="overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/90 shadow-[0_24px_80px_-40px_rgba(15,23,42,0.35)] backdrop-blur">
          <div className="relative p-6 sm:p-8">
            <div className="absolute inset-x-0 top-0 h-28 bg-[linear-gradient(120deg,rgba(14,165,233,0.14),rgba(56,189,248,0.08),rgba(255,255,255,0))]" />
            <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-3xl">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">
                    <Waves className="h-3.5 w-3.5" />
                    Operations Console
                  </span>
                  <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500">
                    마지막 갱신 {fmtDate(lastUpdated)}
                  </span>
                </div>
                <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
                  관리자 패널
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 sm:text-base">
                  문서 인덱싱, 파이프라인 실패, 사용자 활성도, 운영 신호를 한 화면에서 추적하는 온프렘 AI 운영 콘솔입니다.
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:items-end">
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => loadAdminData(true)}
                    disabled={isRefreshing}
                    className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-70"
                  >
                    <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
                    새로고침
                  </button>
                  <button
                    onClick={() => setAutoRefresh((prev) => !prev)}
                    className={`inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition ${
                      autoRefresh
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : "border-slate-200 bg-white text-slate-600"
                    }`}
                  >
                    <Activity className="h-4 w-4" />
                    자동 새로고침 {autoRefresh ? "ON" : "OFF"}
                  </button>
                  <button
                    onClick={() => router.push("/chat")}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
                  >
                    채팅으로 이동
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">System Health Score</p>
                  <div className="mt-2 flex items-end gap-3">
                    <div className="text-3xl font-semibold text-slate-950">{healthScore}</div>
                    <div className="mb-1 text-sm text-slate-500">/ 100</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {loadError && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
            {loadError}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {(["overview", "documents", "users", "pipeline"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                activeTab === tab
                  ? "bg-slate-900 text-white shadow-lg shadow-slate-300/40"
                  : "border border-slate-200 bg-white/80 text-slate-600 hover:bg-white"
              }`}
            >
              {tab === "overview"
                ? "운영 개요"
                : tab === "documents"
                  ? "문서"
                  : tab === "users"
                    ? "사용자"
                    : "파이프라인"}
            </button>
          ))}
        </div>

        {activeTab === "overview" && summary && (
          <div className="space-y-6">
            <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Document Health</p>
                    <h2 className="mt-2 text-xl font-semibold text-slate-950">문서 인덱싱 상태</h2>
                  </div>
                  <div className="rounded-2xl bg-slate-100 px-3 py-2 text-right">
                    <p className="text-xs text-slate-500">인덱싱 성공률</p>
                    <p className="text-lg font-semibold text-slate-900">
                      {summary.documents.total > 0
                        ? Math.round((summary.documents.indexed / summary.documents.total) * 100)
                        : 0}
                      %
                    </p>
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
                  {docCards.map(({ key, label, tone, surface, filter }) => (
                    <button
                      key={label}
                      onClick={() => {
                        setActiveTab("documents");
                        setDocumentFilter(filter);
                      }}
                      className={`rounded-3xl border border-slate-200 bg-gradient-to-br ${surface} p-5 text-left transition hover:-translate-y-0.5 hover:shadow-md`}
                    >
                      <p className="text-sm text-slate-500">{label}</p>
                      <p className={`mt-3 text-3xl font-semibold ${tone}`}>{summary.documents[key]}</p>
                      <p className="mt-3 text-xs font-medium text-slate-500">문서 탭에서 상세 보기</p>
                    </button>
                  ))}
                </div>

                <div className="mt-6">
                  <div className="mb-2 flex items-center justify-between text-sm text-slate-500">
                    <span>인덱싱 진행도</span>
                    <span>
                      {summary.documents.indexed} / {summary.documents.total}
                    </span>
                  </div>
                  <div className="h-3 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-[linear-gradient(90deg,#0f172a,#0ea5e9)]"
                      style={{
                        width:
                          summary.documents.total > 0
                            ? `${(summary.documents.indexed / summary.documents.total) * 100}%`
                            : "0%",
                      }}
                    />
                  </div>
                </div>
              </section>

              <section className="rounded-[28px] border border-slate-200 bg-[linear-gradient(180deg,#0f172a,#172554)] p-6 text-white shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-sky-200/80">Attention</p>
                    <h2 className="mt-2 text-xl font-semibold">현재 확인이 필요한 항목</h2>
                  </div>
                  <AlertTriangle className="h-5 w-5 text-amber-300" />
                </div>

                <div className="mt-5 space-y-4">
                  <button
                    onClick={() => jumpToPipeline("failed")}
                    className="w-full rounded-2xl border border-white/10 bg-white/5 p-4 text-left transition hover:bg-white/10"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-sky-100">최근 파이프라인 실패</span>
                      <span className="text-2xl font-semibold">{failureCount}</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-300">
                      실패 로그와 오류 메시지를 바로 확인할 수 있도록 파이프라인 탭으로 연결합니다.
                    </p>
                  </button>

                  <button
                    onClick={() => jumpToPipeline("all")}
                    className="w-full rounded-2xl border border-white/10 bg-white/5 p-4 text-left transition hover:bg-white/10"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-sky-100">24시간 에러 이벤트</span>
                      <span className="text-2xl font-semibold">{summary.event_errors_24h}</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-300">
                      event_log 기준의 운영 신호입니다. 오류 원인은 파이프라인과 문서 상세에서 추적할 수 있습니다.
                    </p>
                  </button>

                  <button
                    onClick={() => jumpToPipeline("running")}
                    className="w-full rounded-2xl border border-white/10 bg-white/5 p-4 text-left transition hover:bg-white/10"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-sky-100">실행 중 파이프라인</span>
                      <span className="text-2xl font-semibold">{summary.pipeline_running_count}</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-300">
                      작업이 길게 유지되면 병목 지점을 확인해 주세요.
                    </p>
                  </button>
                </div>
              </section>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {metricCard(
                "Queries",
                summary.queries_7d,
                "최근 7일 동안 저장된 질의 로그입니다.",
                "bg-blue-50 text-blue-700",
                <Activity className="h-5 w-5" />,
              )}
              {metricCard(
                "Active Users",
                summary.active_users_7d,
                "7일 기준 질의를 남긴 사용자 수입니다.",
                "bg-indigo-50 text-indigo-700",
                <Users className="h-5 w-5" />,
                () => setActiveTab("users"),
              )}
              {metricCard(
                "Running Jobs",
                summary.pipeline_running_count,
                "`pipeline_logs.status=running` 기준 집계입니다.",
                "bg-cyan-50 text-cyan-700",
                <Database className="h-5 w-5" />,
                () => jumpToPipeline("running"),
              )}
              {metricCard(
                "Error Signals",
                summary.event_errors_24h,
                "최근 24시간 에러 이벤트 수입니다.",
                "bg-rose-50 text-rose-700",
                <ShieldCheck className="h-5 w-5" />,
                () => jumpToPipeline("failed"),
              )}
            </div>

            <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
              <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Recent Documents</p>
                    <h2 className="mt-2 text-xl font-semibold text-slate-950">최근 문서 큐</h2>
                  </div>
                  <button
                    onClick={() => setActiveTab("documents")}
                    className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-white"
                  >
                    문서 탭 열기
                  </button>
                </div>

                <div className="mt-6 space-y-3">
                  {documents.slice(0, 6).map((item) => (
                    <button
                      key={item.doc_id}
                      onClick={() => openDocumentDetail(item.doc_id)}
                      className="flex w-full items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-left transition hover:bg-white"
                    >
                      <div className="min-w-0">
                        <div className="truncate font-medium text-slate-950">{item.file_name}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                          <span>{item.type.toUpperCase()}</span>
                          <span>페이지 {item.total_page_cnt}</span>
                          <span>청크 {item.chunk_count}</span>
                          <span>{fmtDate(item.updated_at)}</span>
                        </div>
                      </div>
                      <span className={`rounded-full border px-2 py-1 text-xs font-medium ${statusPill(item.status)}`}>
                        {item.status}
                      </span>
                    </button>
                  ))}
                  {documents.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-400">
                      등록된 문서가 없습니다.
                    </div>
                  )}
                </div>
              </section>

              <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Module Signals</p>
                    <h2 className="mt-2 text-xl font-semibold text-slate-950">모듈 상태</h2>
                  </div>
                  <ShieldCheck className="h-5 w-5 text-slate-400" />
                </div>
                <div className="mt-6 grid gap-3">
                  {moduleStats.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-400">
                      표시할 모듈 통계가 없습니다.
                    </div>
                  )}
                  {moduleStats.map((item) => (
                    <button
                      key={item.module}
                      onClick={() =>
                        jumpToPipeline(item.errors > 0 ? "failed" : "all", inferStageFromModule(item.module))
                      }
                      className={`rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-sm ${moduleTone(item)}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="font-medium text-slate-950">{item.module}</div>
                          <div className="mt-1 text-sm text-slate-500">
                            평균 duration {item.avg_duration_ms ? `${item.avg_duration_ms} ms` : "-"}
                          </div>
                        </div>
                        <div className="text-right text-sm">
                          <div className="text-slate-600">이벤트 {item.total_events}</div>
                          <div className="text-rose-600">에러 {item.errors}</div>
                          <div className="text-amber-600">경고 {item.warnings}</div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            </div>

            <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
              <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Recent Sync</p>
                    <h2 className="mt-2 text-xl font-semibold text-slate-950">동기화 타임라인</h2>
                  </div>
                  <Clock3 className="h-5 w-5 text-slate-400" />
                </div>
                <div className="mt-6 space-y-4">
                  {summary.recent_sync_runs.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-400">
                      최근 동기화 이력이 없습니다.
                    </div>
                  )}
                  {summary.recent_sync_runs.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => jumpToPipeline("all")}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-left transition hover:bg-white"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <span className={`rounded-full border px-2 py-1 text-xs font-medium ${statusPill(item.status)}`}>
                            {item.status || "unknown"}
                          </span>
                          <span className="font-medium text-slate-900">{item.sync_type || "sync"}</span>
                        </div>
                        <span className="text-xs text-slate-400">{fmtDate(item.started_at)}</span>
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                        <div className="rounded-xl bg-white px-3 py-2 text-slate-600">
                          추가 <span className="font-semibold text-slate-950">{item.files_added}</span>
                        </div>
                        <div className="rounded-xl bg-white px-3 py-2 text-slate-600">
                          수정 <span className="font-semibold text-slate-950">{item.files_modified}</span>
                        </div>
                        <div className="rounded-xl bg-white px-3 py-2 text-slate-600">
                          삭제 <span className="font-semibold text-slate-950">{item.files_deleted}</span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </section>

              <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Recent Failures</p>
                    <h2 className="mt-2 text-xl font-semibold text-slate-950">최근 파이프라인 실패</h2>
                  </div>
                  <AlertTriangle className="h-5 w-5 text-rose-400" />
                </div>

                <div className="mt-6 space-y-3">
                  {summary.recent_pipeline_failures.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-400">
                      최근 실패 이력이 없습니다.
                    </div>
                  )}
                  {summary.recent_pipeline_failures.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => {
                        const fullLog = pipelineLogs.find((log) => log.id === item.id);
                        if (fullLog) openPipelineDetail(fullLog);
                        else jumpToPipeline("failed");
                      }}
                      className="w-full rounded-2xl border border-rose-100 bg-rose-50/70 px-4 py-4 text-left transition hover:bg-white"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate font-medium text-slate-950">
                            {item.doc_file_name || `문서 #${item.doc_id ?? "-"}`}
                          </div>
                          <div className="mt-1 text-xs uppercase tracking-[0.16em] text-rose-600">{item.stage}</div>
                        </div>
                        <div className="text-xs text-slate-400">{fmtDate(item.started_at)}</div>
                      </div>
                      <p className="mt-3 line-clamp-2 text-sm text-slate-600">{item.error_message || "오류 메시지 없음"}</p>
                    </button>
                  ))}
                </div>
              </section>
            </div>
          </div>
        )}

        {activeTab === "documents" && (
          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Documents</p>
                <h2 className="mt-2 text-xl font-semibold text-slate-950">문서 운영 뷰</h2>
                <p className="mt-2 text-sm text-slate-500">
                  문서 상태, 청크 수, 이미지 수, Graph 엔티티 수를 기준으로 처리 품질을 확인할 수 있습니다.
                </p>
              </div>

              <div className="flex w-full flex-col gap-3 xl:max-w-3xl xl:flex-row xl:items-center xl:justify-end">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    value={documentQuery}
                    onChange={(event) => setDocumentQuery(event.target.value)}
                    placeholder="파일명, 경로, 부서, 타입 검색"
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 py-3 pl-11 pr-4 text-sm text-slate-700 outline-none transition focus:border-sky-300 focus:bg-white"
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  {(["all", "indexed", "pending", "failed"] as const).map((item) => (
                    <button
                      key={item}
                      onClick={() => setDocumentFilter(item)}
                      className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                        documentFilter === item
                          ? "bg-slate-900 text-white"
                          : "border border-slate-200 bg-slate-50 text-slate-600 hover:bg-white"
                      }`}
                    >
                      {item === "all" ? "전체" : item === "indexed" ? "완료" : item === "pending" ? "대기" : "실패"}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-4">
              {docCards.map(({ key, label, tone, surface, filter }) => (
                <button
                  key={label}
                  onClick={() => setDocumentFilter(filter)}
                  className={`rounded-3xl border border-slate-200 bg-gradient-to-br ${surface} p-5 text-left transition hover:-translate-y-0.5 hover:shadow-md`}
                >
                  <p className="text-sm text-slate-500">{label}</p>
                  <p className={`mt-3 text-3xl font-semibold ${tone}`}>{summary?.documents[key] ?? 0}</p>
                </button>
              ))}
            </div>

            <div className="mt-6 overflow-x-auto rounded-3xl border border-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-[0.18em] text-slate-500">
                  <tr>
                    {["문서", "타입", "상태", "페이지", "청크/이미지/엔티티", "업데이트", "오류"].map((header) => (
                      <th key={header} className="px-5 py-4">{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredDocuments.map((item) => (
                    <tr
                      key={item.doc_id}
                      onClick={() => openDocumentDetail(item.doc_id)}
                      className="cursor-pointer transition hover:bg-slate-50/90"
                    >
                      <td className="px-5 py-4">
                        <div className="min-w-[220px]">
                          <div className="font-medium text-slate-950">{item.file_name}</div>
                          <div className="mt-1 text-xs text-slate-500">
                            #{item.doc_id} · {item.dept_name || "-"} · {item.role_name || "-"}
                          </div>
                          <div className="mt-1 truncate text-xs text-slate-400">{item.path}</div>
                        </div>
                      </td>
                      <td className="px-5 py-4 text-slate-600">{item.type.toUpperCase()}</td>
                      <td className="px-5 py-4">
                        <span className={`rounded-full border px-2 py-1 text-xs font-medium ${statusPill(item.status)}`}>
                          {item.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-slate-600">{item.total_page_cnt}</td>
                      <td className="px-5 py-4 text-slate-600">
                        {item.chunk_count} / {item.image_count} / {item.entity_count}
                      </td>
                      <td className="px-5 py-4 text-slate-500">{fmtDate(item.updated_at)}</td>
                      <td className="max-w-sm px-5 py-4 text-slate-500">{item.error_msg || "-"}</td>
                    </tr>
                  ))}
                  {filteredDocuments.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-5 py-10 text-center text-slate-400">
                        조건에 맞는 문서가 없습니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {activeTab === "users" && (
          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Users</p>
                <h2 className="mt-2 text-xl font-semibold text-slate-950">사용자 현황</h2>
                <p className="mt-2 text-sm text-slate-500">
                  최근 로그인과 활성 상태를 기준으로 운영 계정을 빠르게 점검할 수 있습니다.
                </p>
              </div>
              <div className="flex gap-3">
                <div className="rounded-2xl bg-slate-100 px-4 py-3 text-sm text-slate-600">
                  전체 <span className="font-semibold text-slate-950">{users.length}</span>
                </div>
                <div className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  활성 <span className="font-semibold">{users.filter((item) => item.is_active).length}</span>
                </div>
              </div>
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="overflow-x-auto rounded-3xl border border-slate-200">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase tracking-[0.18em] text-slate-500">
                    <tr>
                      {["이름", "이메일", "역할", "부서", "상태", "최근 로그인"].map((header) => (
                        <th key={header} className="px-5 py-4">{header}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {users.map((item) => (
                      <tr key={item.user_id} className="hover:bg-slate-50/80">
                        <td className="px-5 py-4 font-medium text-slate-950">{item.usr_name}</td>
                        <td className="px-5 py-4 text-slate-600">{item.email}</td>
                        <td className="px-5 py-4 text-slate-600">{item.role_name}</td>
                        <td className="px-5 py-4 text-slate-600">{item.dept_name}</td>
                        <td className="px-5 py-4">
                          <span
                            className={`rounded-full border px-2 py-1 text-xs font-medium ${
                              item.is_active
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                : "border-rose-200 bg-rose-50 text-rose-700"
                            }`}
                          >
                            {item.is_active ? "활성" : "비활성"}
                          </span>
                        </td>
                        <td className="px-5 py-4 text-slate-500">{fmtDate(item.last_login)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Most Visible</p>
                <h3 className="mt-2 text-lg font-semibold text-slate-950">최근 계정 샘플</h3>
                <div className="mt-4 space-y-3">
                  {topUsers.map((item) => (
                    <div key={item.user_id} className="rounded-2xl bg-white p-4 shadow-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="font-medium text-slate-950">{item.usr_name}</div>
                          <div className="mt-1 text-sm text-slate-500">{item.email}</div>
                        </div>
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
                          {item.role_name}
                        </span>
                      </div>
                      <div className="mt-3 text-sm text-slate-500">{item.dept_name}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        )}

        {activeTab === "pipeline" && (
          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Pipeline</p>
                  <h2 className="mt-2 text-xl font-semibold text-slate-950">최근 파이프라인 로그</h2>
                  <p className="mt-2 text-sm text-slate-500">
                    실패, 실행 중, 성공 상태를 분리하고 문서 상세로 바로 연결할 수 있습니다.
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {(["all", "failed", "running", "success"] as const).map((item) => (
                    <button
                      key={item}
                      onClick={() => setPipelineFilter(item)}
                      className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                        pipelineFilter === item
                          ? "bg-slate-900 text-white"
                          : "border border-slate-200 bg-slate-50 text-slate-600 hover:bg-white"
                      }`}
                    >
                      {item === "all" ? "전체" : item === "failed" ? "실패" : item === "running" ? "실행중" : "성공"}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {availableStages.map((stage) => (
                  <button
                    key={stage}
                    onClick={() => setPipelineStageFilter(stage)}
                    className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                      pipelineStageFilter === stage
                        ? "border border-sky-900 bg-sky-900 text-white"
                        : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {stage === "all" ? "전체 스테이지" : stage}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-6 overflow-x-auto rounded-3xl border border-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-[0.18em] text-slate-500">
                  <tr>
                    {["문서", "스테이지", "상태", "시작", "종료", "오류"].map((header) => (
                      <th key={header} className="px-5 py-4">{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredPipelineLogs.map((item) => (
                    <tr
                      key={item.id}
                      onClick={() => openPipelineDetail(item)}
                      className="cursor-pointer transition hover:bg-slate-50/80"
                    >
                      <td className="px-5 py-4">
                        <div className="min-w-[180px]">
                          <div className="font-medium text-slate-950">{item.doc_file_name || item.doc_id || "-"}</div>
                          <div className="mt-1 text-xs text-slate-500">log #{item.id}</div>
                        </div>
                      </td>
                      <td className="px-5 py-4 text-slate-600">{item.stage}</td>
                      <td className="px-5 py-4">
                        <span className={`rounded-full border px-2 py-1 text-xs font-medium ${statusPill(item.status)}`}>
                          {item.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-slate-500">{fmtDate(item.started_at)}</td>
                      <td className="px-5 py-4 text-slate-500">{fmtDate(item.finished_at)}</td>
                      <td className="max-w-sm px-5 py-4 text-slate-500">{item.error_message || "-"}</td>
                    </tr>
                  ))}
                  {filteredPipelineLogs.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-10 text-center text-slate-400">
                        선택한 조건에 맞는 파이프라인 로그가 없습니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>

      {(selectedDocument || selectedPipelineLog) && (
        <div className="fixed inset-0 z-40 bg-slate-950/30 backdrop-blur-[1px]">
          <button
            aria-label="Close panel"
            onClick={() => {
              setSelectedDocument(null);
              setSelectedPipelineLog(null);
            }}
            className="absolute inset-0"
          />
        </div>
      )}

      {selectedDocument && (
        <aside className="fixed right-0 top-0 z-50 h-full w-full max-w-2xl overflow-y-auto border-l border-slate-200 bg-white shadow-2xl shadow-slate-900/20">
          <div className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-6 py-5 backdrop-blur">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Document Detail</p>
                <h3 className="mt-2 text-2xl font-semibold text-slate-950">{selectedDocument.file_name}</h3>
                <p className="mt-2 text-sm text-slate-500">문서 #{selectedDocument.doc_id}</p>
              </div>
              <button
                onClick={() => setSelectedDocument(null)}
                className="rounded-full border border-slate-200 bg-white p-2 text-slate-500 transition hover:bg-slate-50"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="space-y-6 p-6">
            {isDocumentLoading && (
              <div className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
                문서 상세 정보를 새로 불러오는 중입니다.
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Status</p>
                <div className="mt-3">
                  <span className={`rounded-full border px-3 py-1.5 text-sm font-medium ${statusPill(selectedDocument.status)}`}>
                    {selectedDocument.status}
                  </span>
                </div>
                <div className="mt-4 text-sm text-slate-600">
                  <div>타입 {selectedDocument.type.toUpperCase()}</div>
                  <div className="mt-1">언어 {selectedDocument.language || "-"}</div>
                  <div className="mt-1">사이즈 {formatBytes(selectedDocument.size)}</div>
                </div>
              </div>

              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Signals</p>
                <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                  <div className="rounded-2xl bg-white px-3 py-3 text-slate-600">
                    청크 <div className="mt-1 text-xl font-semibold text-slate-950">{selectedDocument.chunk_count}</div>
                  </div>
                  <div className="rounded-2xl bg-white px-3 py-3 text-slate-600">
                    이미지 <div className="mt-1 text-xl font-semibold text-slate-950">{selectedDocument.image_count}</div>
                  </div>
                  <div className="rounded-2xl bg-white px-3 py-3 text-slate-600">
                    엔티티 <div className="mt-1 text-xl font-semibold text-slate-950">{selectedDocument.entity_count}</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Metadata</p>
              <div className="mt-4 grid gap-4 text-sm text-slate-600 md:grid-cols-2">
                <div>
                  <div className="text-slate-400">부서</div>
                  <div className="mt-1 font-medium text-slate-950">{selectedDocument.dept_name || "-"}</div>
                </div>
                <div>
                  <div className="text-slate-400">권한 역할</div>
                  <div className="mt-1 font-medium text-slate-950">{selectedDocument.role_name || "-"}</div>
                </div>
                <div>
                  <div className="text-slate-400">폴더</div>
                  <div className="mt-1 font-medium text-slate-950">{selectedDocument.folder_name || "-"}</div>
                </div>
                <div>
                  <div className="text-slate-400">페이지 수</div>
                  <div className="mt-1 font-medium text-slate-950">{selectedDocument.total_page_cnt}</div>
                </div>
                <div>
                  <div className="text-slate-400">생성</div>
                  <div className="mt-1 font-medium text-slate-950">{fmtDate(selectedDocument.created_at)}</div>
                </div>
                <div>
                  <div className="text-slate-400">업데이트</div>
                  <div className="mt-1 font-medium text-slate-950">{fmtDate(selectedDocument.updated_at)}</div>
                </div>
              </div>
              <div className="mt-5">
                <div className="text-slate-400">경로</div>
                <div className="mt-1 break-all rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
                  {selectedDocument.path}
                </div>
              </div>
              {selectedDocument.error_msg && (
                <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {selectedDocument.error_msg}
                </div>
              )}
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Recent Pipeline</p>
                  <h4 className="mt-2 text-lg font-semibold text-slate-950">최근 파이프라인 이력</h4>
                </div>
                <button
                  onClick={() => {
                    setSelectedDocument(null);
                    jumpToPipeline("all");
                  }}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-white"
                >
                  전체 로그 보기
                </button>
              </div>

              <div className="mt-4 space-y-3">
                {selectedDocument.recent_pipeline_logs.length === 0 && (
                  <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-400">
                    이 문서의 파이프라인 이력이 없습니다.
                  </div>
                )}
                {selectedDocument.recent_pipeline_logs.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      setSelectedDocument(null);
                      setSelectedPipelineLog(item);
                      setActiveTab("pipeline");
                    }}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-left transition hover:bg-white"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-medium text-slate-950">{item.stage}</div>
                      <span className={`rounded-full border px-2 py-1 text-xs font-medium ${statusPill(item.status)}`}>
                        {item.status}
                      </span>
                    </div>
                    <div className="mt-2 text-sm text-slate-500">{fmtDate(item.started_at)}</div>
                    {item.error_message && <div className="mt-2 text-sm text-rose-700">{item.error_message}</div>}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </aside>
      )}

      {selectedPipelineLog && !selectedDocument && (
        <aside className="fixed right-0 top-0 z-50 h-full w-full max-w-xl overflow-y-auto border-l border-slate-200 bg-white shadow-2xl shadow-slate-900/20">
          <div className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-6 py-5 backdrop-blur">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Pipeline Detail</p>
                <h3 className="mt-2 text-2xl font-semibold text-slate-950">{selectedPipelineLog.stage}</h3>
                <p className="mt-2 text-sm text-slate-500">log #{selectedPipelineLog.id}</p>
              </div>
              <button
                onClick={() => setSelectedPipelineLog(null)}
                className="rounded-full border border-slate-200 bg-white p-2 text-slate-500 transition hover:bg-slate-50"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="space-y-6 p-6">
            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-400">Document</div>
                  <div className="mt-2 text-lg font-semibold text-slate-950">
                    {selectedPipelineLog.doc_file_name || `문서 #${selectedPipelineLog.doc_id ?? "-"}`}
                  </div>
                </div>
                <span className={`rounded-full border px-3 py-1.5 text-sm font-medium ${statusPill(selectedPipelineLog.status)}`}>
                  {selectedPipelineLog.status}
                </span>
              </div>
              <div className="mt-4 space-y-2 text-sm text-slate-600">
                <div>시작 {fmtDate(selectedPipelineLog.started_at)}</div>
                <div>종료 {fmtDate(selectedPipelineLog.finished_at)}</div>
              </div>
              {selectedPipelineLog.doc_id && (
                <button
                  onClick={() => openDocumentDetail(selectedPipelineLog.doc_id!)}
                  className="mt-5 inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
                >
                  <FileText className="h-4 w-4" />
                  문서 상세 보기
                </button>
              )}
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Error</p>
              <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-700">
                {selectedPipelineLog.error_message || "오류 메시지가 없습니다."}
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Metadata</p>
              <div className="mt-3 rounded-2xl bg-slate-950 px-4 py-4 text-xs leading-6 text-slate-100">
                <pre className="whitespace-pre-wrap break-words">
                  {JSON.stringify(selectedPipelineLog.metadata || {}, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}
