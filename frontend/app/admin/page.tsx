"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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

const statCards = [
  { key: "total" as const, label: "전체", className: "text-blue-600" },
  { key: "indexed" as const, label: "인덱싱 완료", className: "text-green-600" },
  { key: "pending" as const, label: "처리 중", className: "text-yellow-600" },
  { key: "failed" as const, label: "실패", className: "text-red-600" },
];

export default function AdminPage() {
  const { user } = useAuthStore();
  const router = useRouter();
  const [docStats, setDocStats] = useState<DocStats | null>(null);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [activeTab, setActiveTab] = useState<"stats" | "users">("stats");

  useEffect(() => {
    if (!user || user.auth_level < 100) {
      router.push("/chat");
      return;
    }
    api.get("/api/v1/admin/documents/stats").then((r) => setDocStats(r.data)).catch(() => {});
    api.get("/api/v1/admin/users").then((r) => setUsers(r.data)).catch(() => {});
  }, []);

  if (!user || user.auth_level < 100) return null;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">관리자 패널</h1>
          <button onClick={() => router.push("/chat")} className="text-sm text-gray-500 hover:text-gray-700">
            ← 채팅으로 돌아가기
          </button>
        </div>

        <div className="flex gap-2 mb-6">
          {(["stats", "users"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-100 border border-gray-200"
              }`}
            >
              {tab === "stats" ? "문서 현황" : "사용자 관리"}
            </button>
          ))}
        </div>

        {activeTab === "stats" && docStats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {statCards.map(({ key, label, className }) => (
              <div key={label} className="bg-white rounded-xl p-5 border border-gray-200 shadow-sm">
                <p className="text-sm text-gray-500 mb-1">{label}</p>
                <p className={`text-3xl font-bold ${className}`}>{docStats[key]}</p>
              </div>
            ))}
          </div>
        )}

        {activeTab === "users" && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {["이름", "이메일", "역할", "부서", "상태", "최근 로그인"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs text-gray-500 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.map((u) => (
                  <tr key={u.user_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{u.usr_name}</td>
                    <td className="px-4 py-3 text-gray-500">{u.email}</td>
                    <td className="px-4 py-3 text-gray-500">{u.role_name}</td>
                    <td className="px-4 py-3 text-gray-500">{u.dept_name}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs ${u.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                        {u.is_active ? "활성" : "비활성"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {u.last_login ? new Date(u.last_login).toLocaleDateString("ko") : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
