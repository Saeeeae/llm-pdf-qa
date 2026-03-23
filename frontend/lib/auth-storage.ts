import axios from "axios";

export const ACCESS_TOKEN_KEY = "access_token";
export const REFRESH_TOKEN_KEY = "refresh_token";

type ApiBaseResolver = () => string;

let refreshRequest: Promise<string | null> | null = null;

function isBrowser() {
  return typeof window !== "undefined";
}

function decodeJwtPayload(token: string) {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(window.atob(padded)) as { exp?: number };
  } catch {
    return null;
  }
}

function isTokenValid(token: string, bufferSeconds = 30) {
  if (!isBrowser()) return true;
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return true;
  return payload.exp * 1000 > Date.now() + bufferSeconds * 1000;
}

export function getStoredAccessToken() {
  if (!isBrowser()) return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getStoredRefreshToken() {
  if (!isBrowser()) return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function storeAuthTokens(accessToken: string, refreshToken?: string | null) {
  if (!isBrowser()) return;
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (typeof refreshToken === "string" && refreshToken.length > 0) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
}

export function clearAuthTokens() {
  if (!isBrowser()) return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export async function refreshStoredAccessToken(getApiBaseUrl: ApiBaseResolver) {
  if (!isBrowser()) return null;
  if (refreshRequest) return refreshRequest;

  refreshRequest = (async () => {
    const refreshToken = getStoredRefreshToken();
    if (!refreshToken) {
      clearAuthTokens();
      return null;
    }

    try {
      const res = await axios.post(
        `${getApiBaseUrl()}/api/v1/auth/refresh`,
        { refresh_token: refreshToken },
        { headers: { "Content-Type": "application/json" } }
      );

      const accessToken = res.data?.access_token;
      if (!accessToken) {
        clearAuthTokens();
        return null;
      }

      storeAuthTokens(accessToken, refreshToken);
      return accessToken;
    } catch {
      clearAuthTokens();
      return null;
    } finally {
      refreshRequest = null;
    }
  })();

  return refreshRequest;
}

export async function ensureValidAccessToken(getApiBaseUrl: ApiBaseResolver) {
  const accessToken = getStoredAccessToken();
  if (!accessToken) return null;
  if (isTokenValid(accessToken)) return accessToken;
  return refreshStoredAccessToken(getApiBaseUrl);
}
