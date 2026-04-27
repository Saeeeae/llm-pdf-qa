"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../lib/auth";
import { t } from "../../lib/i18n";
import { useToastStore } from "../../components/Toast";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const pushToast = useToastStore((s) => s.push);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      router.replace("/chat");
    } catch (err: unknown) {
      const apiErr = err as { status?: number; message?: string };
      if (apiErr?.status === 429) {
        setError(t("login.error.lockout"));
      } else if (apiErr?.status === 401 || apiErr?.status === 400) {
        setError(t("login.error.invalid"));
      } else {
        setError(t("login.error.generic"));
        pushToast({ message: t("login.error.generic"), type: "error" });
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-md p-8">
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">{t("login.title")}</h1>

        <form onSubmit={handleSubmit} noValidate>
          <div className="mb-4">
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              {t("login.email")}
            </label>
            <input
              ref={emailRef}
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-describedby={error ? "login-error" : undefined}
            />
          </div>

          <div className="mb-6">
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              {t("login.password")}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {error && (
            <p id="login-error" role="alert" className="text-red-600 text-sm mb-4">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-medium py-2 px-4 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            {loading ? "..." : t("login.submit")}
          </button>
        </form>
      </div>
    </main>
  );
}
