import { api } from "@/lib/apiClient";
import { User, UserCreate, UserUpdate } from "../types";

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
};
