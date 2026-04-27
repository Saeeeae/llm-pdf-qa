"use client";
import { useAuth } from "../lib/auth";

export function TopBar() {
  const { user, logout } = useAuth();
  return (
    <header className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-6 flex-shrink-0">
      <span className="text-sm font-semibold text-gray-800">RAG Admin</span>
      <div className="flex items-center gap-4">
        {user && (
          <span className="text-xs text-gray-500 truncate max-w-[200px]">{user.email}</span>
        )}
        <button
          onClick={logout}
          aria-label="Sign out"
          className="text-xs text-red-600 hover:text-red-800 focus:outline-none focus:ring-2 focus:ring-red-400 rounded"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
