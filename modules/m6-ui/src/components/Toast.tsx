"use client";
/**
 * Toast.tsx — lightweight toast notifications backed by Zustand.
 * Usage: useToastStore().push({ message: "...", type: "error" })
 */
import { useEffect } from "react";
import { create } from "zustand";
import { clsx } from "clsx";

interface Toast {
  id: string;
  message: string;
  type: "error" | "success" | "info";
}

interface ToastStore {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => void;
  remove: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (t) =>
    set((s) => ({
      toasts: [...s.toasts, { ...t, id: crypto.randomUUID() }],
    })),
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

function ToastItem({ toast }: { toast: Toast }) {
  const remove = useToastStore((s) => s.remove);

  useEffect(() => {
    const timer = setTimeout(() => remove(toast.id), 5000);
    return () => clearTimeout(timer);
  }, [toast.id, remove]);

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={clsx(
        "flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg text-sm text-white",
        {
          "bg-red-600": toast.type === "error",
          "bg-green-600": toast.type === "success",
          "bg-blue-600": toast.type === "info",
        },
      )}
    >
      <span className="flex-1">{toast.message}</span>
      <button
        onClick={() => remove(toast.id)}
        aria-label="Dismiss notification"
        className="text-white/70 hover:text-white transition-colors"
      >
        ✕
      </button>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  if (toasts.length === 0) return null;

  return (
    <div
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}
