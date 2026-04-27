"use client";
import dynamic from "next/dynamic";
import rehypeSanitize from "rehype-sanitize";
import { SourceChip } from "./SourceChip";

// Lazy-load markdown renderer — keeps initial bundle smaller
const Markdown = dynamic(() => import("react-markdown"), { ssr: false });

interface Source {
  title?: string;
  url?: string;
  chunk_id?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  sources?: Source[];
}

interface Props {
  messages: Message[];
  bottomRef: React.RefObject<HTMLDivElement>;
}

export function MessageList({ messages, bottomRef }: Props) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 py-12">
        <p className="text-gray-400 text-sm">No messages yet.</p>
        <div className="flex flex-wrap gap-2 justify-center max-w-md">
          {["What can you help me with?", "Summarize recent documents", "Explain RAG architecture"].map(
            (prompt) => (
              <span
                key={prompt}
                className="px-3 py-1.5 rounded-full bg-gray-100 text-gray-600 text-xs cursor-default select-none"
              >
                {prompt}
              </span>
            ),
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      role="log"
      aria-live="polite"
      aria-label="Chat messages"
      className="flex-1 overflow-y-auto px-4 py-4 space-y-3"
    >
      {messages.map((msg) => (
        <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
          <div
            className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${
              msg.role === "user"
                ? "bg-blue-600 text-white whitespace-pre-wrap"
                : "bg-white border border-gray-200 text-gray-800"
            } ${msg.pending ? "opacity-70" : ""}`}
          >
            {msg.role === "assistant" ? (
              <div className="prose prose-sm max-w-none">
                <Markdown rehypePlugins={[rehypeSanitize]}>{msg.content || (msg.pending ? "Generating response..." : "")}</Markdown>
              </div>
            ) : (
              msg.content
            )}

            {msg.sources && msg.sources.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5 border-t border-gray-100 pt-2">
                {msg.sources.map((s, i) => (
                  <SourceChip key={i} source={s} />
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
