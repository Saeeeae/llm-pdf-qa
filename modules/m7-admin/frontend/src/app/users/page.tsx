"use client";
export const dynamic = "force-dynamic";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { adminApi } from "../../lib/api";

interface UserRow {
  user_id: string;
  email: string;
  name?: string;
  role: string;
  department?: string;
  is_active: boolean;
  last_login_at?: string;
}

function ImpersonateModal({
  user,
  onClose,
}: {
  user: UserRow;
  onClose: () => void;
}) {
  const mut = useMutation({
    mutationFn: () => adminApi.impersonate(user.user_id),
    onSuccess: (data) => {
      alert(`Impersonation token (expires 10 min):\n${data.access_token}`);
      onClose();
    },
    onError: (e) => alert(`Failed: ${e}`),
  });

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Confirm impersonation"
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div className="bg-white rounded-xl p-6 w-96 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold mb-2">Impersonate user?</h2>
        <p className="text-sm text-gray-600 mb-4">
          Issue a 10-minute token for <strong>{user.email}</strong>. Action is audit-logged.
        </p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={() => mut.mutate()}
            disabled={mut.isPending}
            className="px-4 py-2 text-sm rounded-lg bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50"
          >
            {mut.isPending ? "Issuing…" : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const [roleFilter, setRoleFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [impersonating, setImpersonating] = useState<UserRow | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["users", roleFilter, deptFilter],
    queryFn: () => adminApi.users({ role: roleFilter || undefined, department: deptFilter || undefined }),
  });

  const users = (data?.users ?? []) as UserRow[];

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-4">Users</h1>

      <div className="flex gap-3 mb-4">
        <input
          placeholder="Filter by role"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          placeholder="Filter by department"
          value={deptFilter}
          onChange={(e) => setDeptFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}
      {error && <p className="text-sm text-red-500">Error: {String(error)}</p>}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["Email", "Name", "Role", "Department", "Active", "Last Login", ""].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((u) => (
              <tr key={u.user_id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-gray-900">{u.email}</td>
                <td className="px-4 py-3 text-gray-600">{u.name ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-600">{u.department ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className={u.is_active ? "text-green-600" : "text-red-500"}>
                    {u.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : "—"}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => setImpersonating(u)}
                    className="text-xs text-orange-600 hover:text-orange-800 focus:outline-none focus:ring-2 focus:ring-orange-400 rounded"
                  >
                    Impersonate
                  </button>
                </td>
              </tr>
            ))}
            {!isLoading && users.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-400 text-sm">
                  No users found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {impersonating && (
        <ImpersonateModal user={impersonating} onClose={() => setImpersonating(null)} />
      )}
    </div>
  );
}
