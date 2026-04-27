"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/users", label: "Users" },
  { href: "/documents", label: "Documents" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/web-search", label: "Web Search" },
  { href: "/audit-log", label: "Audit Log" },
  { href: "/query-log", label: "Query Log" },
  { href: "/metrics", label: "Metrics" },
  { href: "/health", label: "System Health" },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <nav
      aria-label="Admin navigation"
      className="w-56 bg-white border-r border-gray-200 flex flex-col py-4 flex-shrink-0"
    >
      <div className="px-4 mb-6">
        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Admin</span>
      </div>
      <ul className="flex-1 space-y-0.5 px-2">
        {NAV.map(({ href, label }) => (
          <li key={href}>
            <Link
              href={href}
              className={`block px-3 py-2 rounded-lg text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                path === href
                  ? "bg-blue-50 text-blue-700 font-medium"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
