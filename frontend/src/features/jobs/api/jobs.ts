import { api } from "@/lib/apiClient";
import { Job, JobCreate } from "../types";

export const jobsApi = {
  getAll: async (params?: { limit?: number; skip?: number }) => {
    const response = await api.get<Job[]>("/v1/jobs/", { params });
    return response.data;
  },

  getOne: async (id: string) => {
    const response = await api.get<Job>(`/v1/jobs/${id}`);
    return response.data;
  },

  create: async (data: JobCreate) => {
    const response = await api.post<Job>("/v1/jobs/", data);
    return response.data;
  },

  cancel: async (id: string) => {
    const response = await api.delete<Job>(`/v1/jobs/${id}`);
    return response.data;
  },

  retry: async (id: string) => {
    const response = await api.post<Job>(`/v1/jobs/${id}/retry`);
    return response.data;
  },

  stop: async (id: string) => {
    const response = await api.post<Job>(`/v1/jobs/${id}/cancel`);
    return response.data;
  },

  getAllowedFolders: async () => {
    const response = await api.get<string[]>("/v1/jobs/allowed-folders");
    return response.data;
  },
};
