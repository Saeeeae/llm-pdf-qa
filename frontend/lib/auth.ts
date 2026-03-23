import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "./api";
import {
  clearAuthTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  storeAuthTokens,
} from "./auth-storage";

export interface AuthUser {
  user_id: number;
  usr_name: string;
  email: string;
  role_name: string;
  auth_level: number;
  dept_name: string;
  preferences: Record<string, unknown>;
}

interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  hasHydrated: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<AuthUser | null>;
}

export function resetAuthState() {
  clearAuthTokens();
  useAuthStore.setState({ user: null, isLoading: false });
}

export function getDefaultRouteForUser(user: Pick<AuthUser, "auth_level"> | null | undefined) {
  return user && user.auth_level >= 100 ? "/admin" : "/chat";
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isLoading: false,
      hasHydrated: false,

      login: async (email, password) => {
        set({ isLoading: true });
        try {
          const res = await api.post("/api/v1/auth/login", { email, password });
          const authUser: AuthUser = {
            user_id: res.data.user_id,
            usr_name: res.data.usr_name,
            email: res.data.email,
            role_name: res.data.role_name,
            auth_level: res.data.auth_level,
            dept_name: res.data.dept_name,
            preferences: {},
          };
          storeAuthTokens(res.data.access_token, res.data.refresh_token);
          set({ user: authUser });
          return authUser;
        } finally {
          set({ isLoading: false });
        }
      },

      logout: async () => {
        const refreshToken = getStoredRefreshToken();
        if (refreshToken) {
          await api.post("/api/v1/auth/logout", { refresh_token: refreshToken }).catch(() => {});
        }
        resetAuthState();
      },

      fetchMe: async () => {
        const token = getStoredAccessToken();
        if (!token) {
          set({ user: null });
          return null;
        }
        try {
          const res = await api.get("/api/v1/auth/me");
          set({ user: res.data });
          return res.data;
        } catch {
          resetAuthState();
          return null;
        }
      },
    }),
    {
      name: "auth-store",
      partialize: (s) => ({ user: s.user }),
      onRehydrateStorage: () => () => {
        useAuthStore.setState({ hasHydrated: true });
      },
    }
  )
);
