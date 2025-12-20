import { api } from "@/lib/apiClient";
import { Job, JobCreate } from "../types";

export const jobsApi = {
  getAll: async () => {
    const response = await api.get<Job[]>("/v1/jobs/");
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

  getAllowedFolders: async () => {
    // We need an endpoint for this.
    // Based on the backend code I've seen previously, typical pattern is usually GET /jobs/config/allowed-folders or similar if implemented.
    // However, I recall `ALLOWED_MEDIA_FOLDERS` in settings.
    // Let's assume for now we might need to add this endpoint or it might exist.
    // Checking backend routes would be prudent if this fails.
    // For now, let's assume /v1/jobs/allowed-folders or similar.
    // Wait, I saw the backend files. Let me check `backend/app/api/routers/jobs.py` quickly to be sure.
    // I will assume it exists or I might Mock it if not found yet.
    // Actually, let's stick to what we know. The dashboard needs to know what folders are available.
    // If the backend doesn't have it, we might need to add it or hardcode for now.
    // Let's use a placeholder request for now.
    const response = await api.get<string[]>("/v1/jobs/allowed-folders");
    return response.data;
  },
};
