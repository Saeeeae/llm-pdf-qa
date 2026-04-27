"use client";
import { t } from "../lib/i18n";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen gap-4">
      <h1 className="text-xl font-semibold text-gray-800">{t("error.generic")}</h1>
      <p className="text-sm text-gray-500">{error.message}</p>
      <button
        onClick={reset}
        className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {t("error.retry")}
      </button>
    </main>
  );
}
