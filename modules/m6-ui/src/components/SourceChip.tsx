interface Source {
  title?: string;
  url?: string;
  chunk_id?: string;
}

function safeHref(url?: string): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    if (!["http:", "https:"].includes(u.protocol)) return null;
    return u.toString();
  } catch { return null; }
}

export function SourceChip({ source }: { source: Source }) {
  const label = source.title ?? source.chunk_id ?? "Source";
  const href = safeHref(source.url);
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-100 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors"
        aria-label={`Source: ${label}`}
      >
        {label}
      </a>
    );
  }
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600 border border-gray-200"
      title={source.chunk_id}
    >
      {label}
    </span>
  );
}
