/**
 * middleware.ts — Next.js Edge middleware.
 * Redirects to /login if the session cookie is absent on protected routes.
 * M1 sets Set-Cookie: session=<token>; HttpOnly; Secure; SameSite=Lax on login.
 * The middleware only checks cookie presence — full JWT verification happens server-side.
 */
import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = new Set(["/login"]);

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();

  // session cookie presence check (httpOnly set by M1 /auth/login)
  const hasSession =
    req.cookies.has("session") || req.cookies.has("refresh_token");

  if (!hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/).*)"],
};
