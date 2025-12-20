import { api } from "@/lib/apiClient";
import { StoragePath, StoragePathCreate } from "../types";

export const pathsApi = {
  getAll: async () => {
    const response = await api.get<StoragePath[]>("/v1/storage-paths/");
    return response.data;
  },

  create: async (data: StoragePathCreate) => {
    const response = await api.post<StoragePath>("/v1/storage-paths/", data);
    return response.data;
  },

  delete: async (id: string) => {
    await api.delete(`/v1/storage-paths/${id}`);
  },
};
