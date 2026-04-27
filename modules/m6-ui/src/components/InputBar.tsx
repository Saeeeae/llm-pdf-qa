"use client";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onAbort: () => void;
  streaming: boolean;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
}

export function InputBar({ value, onChange, onSend, onAbort, streaming, textareaRef }: Props) {
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSend();
        }}
        className="flex items-end gap-2"
      >
        <label htmlFor="chat-input" className="sr-only">
          Type a message
        </label>
        <textarea
          id="chat-input"
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message"
          rows={1}
          disabled={streaming}
          aria-label="Type a message"
          className="flex-1 border border-gray-300 rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 motion-safe:transition-colors"
          style={{ maxHeight: "8rem", overflowY: "auto" }}
        />

        {streaming ? (
          <button
            type="button"
            onClick={onAbort}
            aria-label="Stop generating"
            className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm rounded-xl focus:outline-none focus:ring-2 focus:ring-red-500 transition-colors"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!value.trim()}
            aria-label="Send message"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
          >
            Send
          </button>
        )}
      </form>
    </div>
  );
}
