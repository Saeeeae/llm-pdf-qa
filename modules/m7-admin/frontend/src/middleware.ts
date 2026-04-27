/**
 * middleware.ts — Next.js Edge middleware for M7 admin frontend.
 * Redirects to M6 login if the session cookie is absent.
 */
import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = new Set(["/login"]);
const DEV_AUTH =
  process.env.NEXT_PUBLIC_DEV_AUTH === "1" ||
  process.env.NEXT_PUBLIC_USE_MOCKS === "1";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();
  if (DEV_AUTH) return NextResponse.next();

  const hasSession =
    req.cookies.has("session") || req.cookies.has("refresh_token");

  if (!hasSession) {
    const m6Login =
      process.env.NEXT_PUBLIC_M6_URL
        ? `${process.env.NEXT_PUBLIC_M6_URL}/login`
        : "http://localhost:3000/login";
    return NextResponse.redirect(m6Login);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};
