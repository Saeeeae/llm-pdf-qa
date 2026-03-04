import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText } from "lucide-react";

interface Reference {
  doc_id: number;
  file_name: string;
  page: number | null;
  score: number;
}

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  references?: Reference[];
  isStreaming?: boolean;
}

export default function ChatMessage({ role, content, references, isStreaming }: ChatMessageProps) {
  return (
    <div className={`flex gap-3 py-3 ${role === "user" ? "justify-end" : "justify-start"}`}>
      {role === "assistant" && (
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold shrink-0 mt-1">
          AI
        </div>
      )}

      <div className={`max-w-[75%] space-y-2 ${role === "user" ? "items-end flex flex-col" : ""}`}>
        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
            role === "user"
              ? "bg-blue-600 text-white"
              : "bg-white border border-gray-200 text-gray-800 shadow-sm"
          }`}
        >
          {role === "assistant" ? (
            <div className="prose prose-sm max-w-none prose-p:my-1 prose-pre:my-2">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              {isStreaming && (
                <span className="inline-block w-1.5 h-4 bg-gray-400 animate-pulse ml-0.5 align-middle" />
              )}
            </div>
          ) : (
            <p className="whitespace-pre-wrap">{content}</p>
          )}
        </div>

        {references && references.length > 0 && (
          <div className="space-y-1 w-full">
            <p className="text-xs text-gray-400 px-1">참고 문서</p>
            {references.map((ref, i) => (
              <div
                key={i}
                className="flex items-center gap-2 text-xs text-gray-500 bg-gray-50 px-3 py-1.5 rounded-lg border border-gray-100"
              >
                <FileText size={11} className="shrink-0 text-gray-400" />
                <span className="truncate flex-1">{ref.file_name}</span>
                {ref.page && <span className="text-gray-400 shrink-0">p.{ref.page}</span>}
                <span className="text-gray-300 shrink-0">{(ref.score * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {role === "user" && (
        <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-gray-600 text-xs font-bold shrink-0 mt-1">
          나
        </div>
      )}
    </div>
  );
}
