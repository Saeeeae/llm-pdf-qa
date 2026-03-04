"use client";

import { useState, useRef } from "react";
import { Send, Globe } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string, options: { searchScope: string; useWebSearch: boolean }) => void;
  isStreaming: boolean;
}

export default function ChatInput({ onSend, isStreaming }: ChatInputProps) {
  const [message, setMessage] = useState("");
  const [searchScope, setSearchScope] = useState("all");
  const [useWebSearch, setUseWebSearch] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    if (!message.trim() || isStreaming) return;
    onSend(message.trim(), { searchScope, useWebSearch });
    setMessage("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="flex items-center gap-3 mb-2 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <span>검색 범위:</span>
          <select
            value={searchScope}
            onChange={(e) => setSearchScope(e.target.value)}
            className="border border-gray-200 rounded px-1.5 py-0.5 text-xs bg-white"
          >
            <option value="all">전체</option>
            <option value="dept">내 부서</option>
          </select>
        </div>
        <button
          onClick={() => setUseWebSearch(!useWebSearch)}
          className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-colors text-xs ${
            useWebSearch ? "border-blue-300 bg-blue-50 text-blue-600" : "border-gray-200 text-gray-400 hover:border-gray-300"
          }`}
        >
          <Globe size={11} />
          웹 검색
        </button>
      </div>

      <div className="flex items-end gap-2 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 focus-within:border-blue-300 transition-colors">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => {
            setMessage(e.target.value);
            if (textareaRef.current) {
              textareaRef.current.style.height = "auto";
              textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
            }
          }}
          onKeyDown={handleKeyDown}
          placeholder="메시지를 입력하세요... (Enter: 전송, Shift+Enter: 줄바꿈)"
          rows={1}
          disabled={isStreaming}
          className="flex-1 bg-transparent text-sm resize-none outline-none min-h-[24px] max-h-[160px] text-gray-800 placeholder-gray-400"
        />
        <button
          onClick={handleSend}
          disabled={!message.trim() || isStreaming}
          className="p-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}
