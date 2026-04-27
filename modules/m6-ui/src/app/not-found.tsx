import Link from "next/link";
import { t } from "../lib/i18n";

export default function NotFound() {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen gap-4">
      <h1 className="text-4xl font-bold text-gray-300">404</h1>
      <p className="text-gray-600">{t("error.not_found")}</p>
      <Link
        href="/"
        className="text-blue-600 hover:underline text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
      >
        홈으로
      </Link>
    </main>
  );
}
