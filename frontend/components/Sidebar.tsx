"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { Plus, MessageSquare, Trash2, LogOut, Settings } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";

interface Session {
  session_id: number;
  title: string | null;
  created_at: string;
  message_count: number;
}

export default function Sidebar() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const router = useRouter();
  const params = useParams();
  const { user, logout } = useAuthStore();
  const currentSessionId = params?.sessionId ? Number(params.sessionId) : null;

  const loadSessions = () => {
    api.get("/api/v1/chat/sessions").then((r) => setSessions(r.data)).catch(() => {});
  };

  useEffect(() => {
    loadSessions();
  }, []);

  const createSession = async () => {
    const res = await api.post("/api/v1/chat/sessions", {});
    setSessions((prev) => [res.data, ...prev]);
    router.push(`/chat/${res.data.session_id}`);
  };

  const deleteSession = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    await api.delete(`/api/v1/chat/sessions/${id}`);
    setSessions((prev) => prev.filter((s) => s.session_id !== id));
    if (currentSessionId === id) router.push("/chat");
  };

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <div className="w-64 h-screen bg-gray-900 text-white flex flex-col shrink-0">
      <div className="p-4 border-b border-gray-700">
        <h1 className="font-semibold text-sm text-gray-200">사내 AI 어시스턴트</h1>
        <p className="text-xs text-gray-500 mt-0.5">{user?.dept_name}</p>
      </div>

      <div className="p-3">
        <button
          onClick={createSession}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-700 text-sm transition-colors border border-gray-700 text-gray-300"
        >
          <Plus size={16} />
          새 대화
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {sessions.map((s) => (
          <div
            key={s.session_id}
            onClick={() => router.push(`/chat/${s.session_id}`)}
            className={`group flex items-center justify-between px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
              currentSessionId === s.session_id ? "bg-gray-700 text-white" : "hover:bg-gray-800 text-gray-400"
            }`}
          >
            <div className="flex items-center gap-2 min-w-0">
              <MessageSquare size={13} className="shrink-0" />
              <span className="truncate">{s.title || "새 대화"}</span>
            </div>
            <button
              onClick={(e) => deleteSession(s.session_id, e)}
              className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition-opacity shrink-0"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>

      <div className="p-3 border-t border-gray-700">
        <div className="flex items-center justify-between">
          <div className="text-xs text-gray-400 min-w-0 mr-2">
            <p className="font-medium text-gray-300 truncate">{user?.usr_name}</p>
            <p className="truncate">{user?.role_name}</p>
          </div>
          <div className="flex gap-1.5 shrink-0">
            {user?.auth_level && user.auth_level >= 100 && (
              <button
                onClick={() => router.push("/admin")}
                className="text-gray-500 hover:text-gray-300 transition-colors"
                title="관리자 패널"
              >
                <Settings size={15} />
              </button>
            )}
            <button
              onClick={handleLogout}
              className="text-gray-500 hover:text-gray-300 transition-colors"
              title="로그아웃"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
