import { api } from "@/lib/apiClient";
import { User, UserUpdate } from "@/features/admin/types";

export const usersApi = {
  // Get current user details
  getMe: async () => {
    const response = await api.get<User>("/v1/users/me");
    return response.data;
  },

  // Update current user
  updateMe: async (data: UserUpdate) => {
    const response = await api.patch<User>("/v1/users/me", data);
    return response.data;
  },

  // Get specific user (usually admin only or public profile if standard)
  getUser: async (id: string) => {
    const response = await api.get<User>(`/v1/users/${id}`);
    return response.data;
  },

  // Update specific user
  updateUser: async (id: string, data: UserUpdate) => {
    const response = await api.patch<User>(`/v1/users/${id}`, data);
    return response.data;
  },

  // Delete specific user
  deleteUser: async (id: string) => {
    await api.delete(`/v1/users/${id}`);
  },
};
