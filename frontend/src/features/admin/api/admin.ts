import { api } from "@/lib/apiClient";
import { User, UserCreate, UserUpdate } from "../types";

export interface OpenSignupResponse {
  open_signup: boolean;
}

export const adminApi = {
  getUsers: async () => {
    const response = await api.get<User[]>("/v1/admin/users");
    return response.data;
  },

  getUser: async (id: string) => {
    const response = await api.get<User>(`/v1/admin/users/${id}`);
    return response.data;
  },

  createUser: async (data: UserCreate) => {
    const response = await api.post<User>("/v1/admin/users", data);
    return response.data;
  },

  updateUser: async (id: string, data: UserUpdate) => {
    const response = await api.patch<User>(`/v1/admin/users/${id}`, data);
    return response.data;
  },

  deleteUser: async (id: string) => {
    await api.delete(`/v1/admin/users/${id}`);
  },

  // Open Signup Settings (Superuser only)
  getOpenSignup: async () => {
    const response = await api.get<OpenSignupResponse>(
      "/v1/admin/settings/open-signup",
    );
    return response.data.open_signup;
  },

  setOpenSignup: async (enabled: boolean) => {
    const response = await api.patch<OpenSignupResponse>(
      "/v1/admin/settings/open-signup",
      { open_signup: enabled },
    );
    return response.data.open_signup;
  },
};
