import { create } from "zustand";
import { persist } from "zustand/middleware";
import { UserPreferences } from "@/features/admin/types";

interface User {
  id: string;
  email: string;
  role: string | null;
  api_key_preview?: string | null;
  is_superuser: boolean;
  force_password_change?: boolean;
  preferences?: UserPreferences;
}

interface AuthState {
  accessToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  setAccessToken: (token: string) => void;
  setUser: (user: User) => void;
  login: (token: string, user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      user: null,
      isAuthenticated: false,
      setAccessToken: (token) => set({ accessToken: token }),
      setUser: (user) => set({ user }),
      login: (token, user) =>
        set({ accessToken: token, user, isAuthenticated: true }),
      logout: () =>
        set({ accessToken: null, user: null, isAuthenticated: false }),
    }),
    {
      name: "auth-storage", // unique name
      // We only persist the user info maybe? Or token too?
      // Security: Storing access token in localStorage is vulnerable to XSS.
      // Ideally we only store it in memory.
      // But for "persistence" across reloads, we need it somewhere or rely on refresh token to get a new one on mount.
      // The plan said: "Store access token in memory (React state/Zustand) instead of localStorage."
      // So we should NOT persist accessToken here if we follow strict security.
      // Use partial persistence.
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      // Actually, if we rely on refresh token, on reload we are "authenticated" but have no access token.
      // We need an "init" check.
      // For now, let's stick to memory for token.
    },
  ),
);
