"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { getDefaultRouteForUser, useAuthStore } from "@/lib/auth";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const { user, fetchMe, hasHydrated } = useAuthStore();
  const router = useRouter();
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const ensureAuth = async () => {
      if (!hasHydrated) return;

      let currentUser = user;
      if (!currentUser) {
        await fetchMe();
        currentUser = useAuthStore.getState().user;
      }

      if (cancelled) return;

      if (!currentUser) {
        router.replace("/login");
        return;
      }

      if (currentUser.auth_level >= 100 && window.location.pathname === "/chat") {
        router.replace(getDefaultRouteForUser(currentUser));
        return;
      }

      setIsCheckingAuth(false);
    };

    ensureAuth();

    return () => {
      cancelled = true;
    };
  }, [fetchMe, hasHydrated, router, user]);

  if (!hasHydrated || isCheckingAuth || !user) {
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
