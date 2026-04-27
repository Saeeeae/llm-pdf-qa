"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { silentRefresh } from "../lib/auth";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    // On app load: attempt silent refresh to restore session from httpOnly cookie
    silentRefresh().then((ok) => {
      router.replace(ok ? "/chat" : "/login");
    });
  }, [router]);

  return (
    <main className="flex items-center justify-center min-h-screen">
      <div className="text-gray-400 text-sm">로딩 중...</div>
    </main>
  );
}
