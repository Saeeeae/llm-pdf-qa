import type { CSSProperties } from "react";

export function Skeleton({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse bg-gray-200 rounded ${className}`}
      style={style}
    />
  );
}

export function MessageSkeleton() {
  return (
    <div className="space-y-3 p-4">
      {[80, 60, 90].map((w, i) => (
        <div key={i} className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}>
          <Skeleton className="h-9 rounded-2xl" style={{ width: `${w}%` }} />
        </div>
      ))}
    </div>
  );
}
