"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { type AuthUser, getDefaultRouteForUser, resetAuthState, useAuthStore } from "@/lib/auth";
import { getStoredAccessToken } from "@/lib/auth-storage";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { fetchMe, hasHydrated } = useAuthStore();
  const router = useRouter();
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const [resolvedUser, setResolvedUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let cancelled = false;

    const ensureAuth = async () => {
      if (!hasHydrated) return;

      const accessToken = getStoredAccessToken();
      if (!accessToken) {
        resetAuthState();
        if (!cancelled) router.replace("/login");
        return;
      }

      const currentUser = await fetchMe();
      if (cancelled) return;

      if (!currentUser) {
        router.replace("/login");
        return;
      }

      if (currentUser.auth_level >= 100) {
        router.replace(getDefaultRouteForUser(currentUser));
        return;
      }

      setResolvedUser(currentUser);
      setIsCheckingAuth(false);
    };

    ensureAuth();

    return () => {
      cancelled = true;
    };
  }, [fetchMe, hasHydrated, router]);

  if (!hasHydrated || isCheckingAuth || !resolvedUser) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-400 text-sm">로딩 중...</div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
