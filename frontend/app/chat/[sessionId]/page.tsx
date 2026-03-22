"use client";

import { useEffect, useRef, useState, use } from "react";
import { api, API_BASE } from "@/lib/api";
import ChatMessage from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";

interface Reference {
  doc_id: number;
  file_name: string;
  page: number | null;
  score: number;
}

interface Message {
  msg_id?: number;
  role: "user" | "assistant";
  content: string;
  references?: Reference[];
  isStreaming?: boolean;
}

export default function ChatPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sessionId) return;
    setMessages([]);
    api
      .get(`/api/v1/chat/sessions/${sessionId}/messages`)
      .then((res) => {
        setMessages(
          res.data.map((m: { msg_id: number; sender_type: string; message: string }) => ({
            msg_id: m.msg_id,
            role: m.sender_type as "user" | "assistant",
            content: m.message,
          }))
        );
      })
      .catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (
    text: string,
    options: { searchScope: string; useWebSearch: boolean }
  ) => {
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "", isStreaming: true }]);
    setIsStreaming(true);

    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

    try {
      const response = await fetch(
        `${API_BASE()}/api/v1/chat/sessions/${sessionId}/stream`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            message: text,
            search_scope: options.searchScope,
            use_web_search: options.useWebSearch,
          }),
        }
      );

      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let currentRefs: Reference[] = [];
      let assistantMsgId: number | undefined;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const lines = decoder.decode(value, { stream: true }).split("\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "token") {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: last.content + data.content };
                return updated;
              });
            } else if (data.type === "references") {
              currentRefs = data.refs;
            } else if (data.type === "done") {
              assistantMsgId = data.msg_id;
            } else if (data.type === "error") {
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  content: `오류가 발생했습니다: ${data.message}`,
                  isStreaming: false,
                };
                return updated;
              });
            }
          } catch {
            // ignore parse errors
          }
        }
      }

      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          isStreaming: false,
          references: currentRefs,
          msg_id: assistantMsgId,
        };
        return updated;
      });
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          content: "연결 오류가 발생했습니다. 다시 시도해주세요.",
          isStreaming: false,
        };
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 mt-16">
              <p className="text-lg">무엇이든 물어보세요</p>
              <p className="text-sm mt-1">사내 문서를 기반으로 답변합니다</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <ChatMessage
              key={i}
              role={msg.role}
              content={msg.content}
              references={msg.references}
              isStreaming={msg.isStreaming}
            />
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="max-w-3xl mx-auto w-full px-0">
        <ChatInput onSend={sendMessage} isStreaming={isStreaming} />
      </div>
    </div>
  );
}
