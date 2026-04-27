"use client";
/**
 * ErrorBoundary.tsx — widget-level error boundary using react-error-boundary.
 * Prevents chat stream failures from crashing the whole chat page.
 */
import { ErrorBoundary as REB, FallbackProps } from "react-error-boundary";

function Fallback({ error, resetErrorBoundary }: FallbackProps) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 flex items-center gap-3"
    >
      <span className="flex-1">{error?.message ?? "An error occurred."}</span>
      <button
        onClick={resetErrorBoundary}
        className="text-xs border border-red-300 rounded px-2 py-1 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-400"
      >
        Retry
      </button>
    </div>
  );
}

export function ErrorBoundary({ children }: { children: React.ReactNode }) {
  return <REB FallbackComponent={Fallback}>{children}</REB>;
}
