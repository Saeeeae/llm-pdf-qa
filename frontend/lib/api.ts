import axios from "axios";

function normalizeBaseUrl(url: string) {
  return url.replace(/\/+$/, "");
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
    return `${window.location.protocol}//${window.location.hostname}:8002`;
  }

  return "http://localhost:8002";
}

export const api = axios.create({
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl();
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
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
      const refreshToken = typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
      if (refreshToken) {
        try {
          const res = await axios.post(`${getApiBaseUrl()}/api/v1/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem("access_token", res.data.access_token);
          config.headers = config.headers ?? {};
          config.headers.Authorization = `Bearer ${res.data.access_token}`;
          return api(config);
        } catch {
          if (typeof window !== "undefined") {
            localStorage.clear();
            window.location.href = "/login";
          }
        }
      }
    }
    return Promise.reject(err);
  }
);

export const API_BASE = getApiBaseUrl;
