import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "RAG Admin",
  description: "RAG-LLM administration dashboard",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="bg-gray-100 text-gray-900 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
