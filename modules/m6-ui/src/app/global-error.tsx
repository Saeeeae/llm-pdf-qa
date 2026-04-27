"use client";
// global-error.tsx catches errors in the root layout itself.
// Must include <html>/<body> tags as it replaces the entire layout.
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="ko">
      <body className="flex flex-col items-center justify-center min-h-screen bg-gray-50 gap-4">
        <h1 className="text-xl font-semibold text-gray-800">오류가 발생했습니다.</h1>
        <p className="text-sm text-gray-500 max-w-md text-center">{error.message}</p>
        <button
          onClick={reset}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          다시 시도
        </button>
      </body>
    </html>
  );
}
