import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { Providers } from "./providers";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";
const IS_DEV = process.env.NODE_ENV !== "production";
const SCRIPT_SRC = ["script-src", "'self'", "'unsafe-inline'", ...(IS_DEV ? ["'unsafe-eval'"] : [])];

export const metadata: Metadata = {
  title: "RAG Chat",
  description: "RAG-powered chat interface",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <head>
        {/* Preconnect to API base to reduce latency */}
        <link rel="preconnect" href={API_BASE} />
        {/* CSP as meta tag — defense-in-depth, primary CSP is set via HTTP headers in next.config.js */}
        <meta
          httpEquiv="Content-Security-Policy"
          content={[
            "default-src 'self'",
            `connect-src 'self' ${API_BASE}`,
            SCRIPT_SRC.join(" "),
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self'",
            "frame-ancestors 'none'",
          ].join("; ")}
        />
      </head>
      <body className="bg-gray-50 text-gray-900 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
