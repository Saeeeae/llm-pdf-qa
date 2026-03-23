import axios from "axios";
import {
  clearAuthTokens,
  getStoredAccessToken,
  refreshStoredAccessToken,
} from "./auth-storage";

function normalizeBaseUrl(url: string) {
  return url.replace(/\/+$/, "");
}

function getDefaultApiPort() {
  const envPort = process.env.NEXT_PUBLIC_API_PORT?.trim();
  return envPort || "8002";
}

function shouldUseEnvUrl(envUrl: string) {
  if (typeof window === "undefined") {
    return true;
  }

  try {
    const parsed = new URL(envUrl);
    const envHost = parsed.hostname;
    const browserHost = window.location.hostname;
    const envIsLocal = envHost === "localhost" || envHost === "127.0.0.1";
    const browserIsLocal = browserHost === "localhost" || browserHost === "127.0.0.1";
    return !(envIsLocal && !browserIsLocal);
  } catch {
    return true;
  }
}

export function getApiBaseUrl() {
  const envUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (envUrl && shouldUseEnvUrl(envUrl)) {
    return normalizeBaseUrl(envUrl);
  }

  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${getDefaultApiPort()}`;
  }

  return `http://localhost:${getDefaultApiPort()}`;
}

export const api = axios.create({
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl();
  if (typeof window !== "undefined") {
    const token = getStoredAccessToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const config = err.config as (typeof err.config & { _retry?: boolean }) | undefined;
    if (err.response?.status === 401 && config && !config._retry) {
      config._retry = true;
      const accessToken = await refreshStoredAccessToken(getApiBaseUrl);
      if (accessToken) {
        config.headers = config.headers ?? {};
        config.headers.Authorization = `Bearer ${accessToken}`;
        return api(config);
      }
      if (typeof window !== "undefined") {
        clearAuthTokens();
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export const API_BASE = getApiBaseUrl;
