import { api } from "@/lib/apiClient";
import { useAuthStore } from "@/store/authStore";

import { RegisterPayload, ResetPasswordPayload } from "../types";

export interface LoginCredentials {
  username: string; // OAuth2PasswordRequestForm expects username
  password: string;
}

export interface UserResponse {
  id: string;
  email: string;
  role?: string;
  is_active?: boolean;
  is_superuser?: boolean;
  is_verified?: boolean;
}

export const authApi = {
  login: async (credentials: LoginCredentials) => {
    // fastpi-users /login endpoint expects x-www-form-urlencoded body usually if using OAuth2PasswordRequestForm
    // But fastapi-users generic transport might expect JSON depending on config.
    // Standard fastapi-users router: POST /login (username, password) as form data.

    // Let's assume standard form data for OAuth2
    const formData = new FormData();
    formData.append("username", credentials.username);
    formData.append("password", credentials.password);

    const response = await api.post("/v1/auth/login", formData, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return response.data;
  },

  logout: async () => {
    await api.post("/v1/auth/logout");
    useAuthStore.getState().logout();
  },

  register: async (data: RegisterPayload) => {
    const response = await api.post<UserResponse>("/v1/auth/register", data);
    return response.data;
  },

  refresh: async () => {
    // Explicit refresh call if needed manually, though interceptor handles usually
    const response = await api.post("/v1/auth/refresh");
    return response.data;
  },

  forgotPassword: async (email: string) => {
    await api.post("/v1/auth/forgot-password", { email });
  },

  resetPassword: async (data: ResetPasswordPayload) => {
    await api.post("/v1/auth/reset-password", data);
  },

  requestVerifyToken: async (email: string) => {
    await api.post("/v1/auth/request-verify-token", { email });
  },

  verify: async (token: string) => {
    await api.post("/v1/auth/verify", { token });
  },

  getMe: async () => {
    const response = await api.get<UserResponse>("/v1/users/me");
    return response.data;
  },
};
