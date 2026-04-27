"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Sidebar } from "../components/Sidebar";
import { TopBar } from "../components/TopBar";
import { silentRefresh } from "../lib/auth";
import { queryClient } from "../lib/queryClient";

function AdminShell({ children }: { children: ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    silentRefresh().then((ok) => {
      if (!ok) {
        const m6Login = process.env.NEXT_PUBLIC_M6_URL
          ? `${process.env.NEXT_PUBLIC_M6_URL}/login`
          : "http://localhost:3000/login";
        router.replace(m6Login);
      }
    });
  }, [router]);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-gray-100">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AdminShell>{children}</AdminShell>
    </QueryClientProvider>
  );
}
