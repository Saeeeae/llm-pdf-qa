"use client";
/**
 * Chat page — session list (left) + message thread (right).
 * Streams SSE from POST /api/v1/chat via fetch + ReadableStream.
 * Abort: AbortController + Stop button.
 * Sources: emitted by SSE event:sources, displayed as SourceChips.
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../lib/auth";
import { streamChat } from "../../lib/sse";
import { t } from "../../lib/i18n";
import { useToastStore } from "../../components/Toast";
import { MessageList, type Message } from "../../components/MessageList";
import { InputBar } from "../../components/InputBar";
import { ErrorBoundary } from "../../components/ErrorBoundary";

interface Session {
  id: string;
  label: string;
}

function newId() {
  return crypto.randomUUID();
}

export default function ChatPage() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const pushToast = useToastStore((s) => s.push);

  const [sessions, setSessions] = useState<Session[]>(() => [{ id: newId(), label: "Chat 1" }]);
  const [activeSessionId, setActiveSessionId] = useState<string>(sessions[0].id);
  const [messagesBySession, setMessagesBySession] = useState<Record<string, Message[]>>({});
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const messages = messagesBySession[activeSessionId] ?? [];

  useEffect(() => {
    if (!user) router.replace("/login");
  }, [user, router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function addMessage(sid: string, msg: Message) {
    setMessagesBySession((prev) => ({ ...prev, [sid]: [...(prev[sid] ?? []), msg] }));
  }

  function updateLastAssistant(sid: string, updater: (m: Message) => Message) {
    setMessagesBySession((prev) => {
      const msgs = [...(prev[sid] ?? [])];
      const idx = msgs.findLastIndex((m) => m.role === "assistant");
      if (idx >= 0) msgs[idx] = updater(msgs[idx]);
      return { ...prev, [sid]: msgs };
    });
  }

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;
    const sid = activeSessionId;
    setInput("");
    setStreaming(true);

    addMessage(sid, { id: newId(), role: "user", content: text });
    addMessage(sid, { id: newId(), role: "assistant", content: "", pending: true });

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        text,
        sid,
        (token) => updateLastAssistant(sid, (m) => ({ ...m, content: m.content + token })),
        (sources) => updateLastAssistant(sid, (m) => ({ ...m, sources })),
        controller.signal,
      );
    } catch (err: unknown) {
      if ((err as Error)?.name !== "AbortError") {
        pushToast({ message: t("chat.error.send"), type: "error" });
        updateLastAssistant(sid, (m) => ({ ...m, content: "[Error]", pending: false }));
      }
    } finally {
      updateLastAssistant(sid, (m) => ({ ...m, pending: false }));
      setStreaming(false);
      abortRef.current = null;
      textareaRef.current?.focus();
    }
  }, [input, streaming, activeSessionId, pushToast]);

  function handleAbort() {
    abortRef.current?.abort();
  }

  function addNewSession() {
    const id = newId();
    const label = `Chat ${sessions.length + 1}`;
    setSessions((prev) => [...prev, { id, label }]);
    setActiveSessionId(id);
  }

  if (!user) return null;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* Skip-to-content — WCAG requirement */}
      <a
        href="#chat-main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-1 focus:bg-white focus:rounded focus:shadow focus:text-blue-600 focus:text-sm"
      >
        Skip to chat
      </a>

      {/* Sidebar */}
      <nav
        aria-label={t("chat.sessions")}
        className="hidden md:flex flex-col w-64 bg-white border-r border-gray-200 p-4 gap-2"
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-gray-700">{t("chat.sessions")}</span>
          <button
            onClick={addNewSession}
            aria-label={t("chat.new_session")}
            className="text-xs text-blue-600 hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
          >
            + {t("chat.new_session")}
          </button>
        </div>

        <ul className="flex-1 overflow-y-auto space-y-1">
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => setActiveSessionId(s.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm truncate focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  s.id === activeSessionId
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                {s.label}
              </button>
            </li>
          ))}
        </ul>

        <div className="border-t border-gray-200 pt-3">
          <p className="text-xs text-gray-500 truncate mb-2">{user.email}</p>
          <button
            onClick={logout}
            aria-label="Sign out"
            className="text-xs text-red-600 hover:text-red-800 focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
          >
            {t("nav.logout")}
          </button>
        </div>
      </nav>

      {/* Main */}
      <main id="chat-main" className="flex flex-col flex-1 overflow-hidden">
        <header className="md:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200">
          <span className="text-sm font-semibold">
            {sessions.find((s) => s.id === activeSessionId)?.label}
          </span>
          <button
            onClick={logout}
            aria-label="Sign out"
            className="text-xs text-red-600 focus:outline-none focus:ring-2 focus:ring-red-500 rounded"
          >
            {t("nav.logout")}
          </button>
        </header>

        <ErrorBoundary>
          <MessageList messages={messages} bottomRef={bottomRef} />
        </ErrorBoundary>

        <InputBar
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onAbort={handleAbort}
          streaming={streaming}
          textareaRef={textareaRef}
        />
      </main>
    </div>
  );
}
