import { api } from "@/lib/apiClient";

export interface ApiKeyCreateResponse {
  id: string;
  api_key: string;
  preview: string;
  created_at: string;
}

export interface ApiKeyRevokeResponse {
  revoked: boolean;
}

export const usersApi = {
  regenerateApiKey: async () => {
    const response = await api.post<ApiKeyCreateResponse>(
      "/v1/users/me/api-key",
    );
    return response.data;
  },
  revokeApiKey: async () => {
    const response = await api.delete<ApiKeyRevokeResponse>(
      "/v1/users/me/api-key",
    );
    return response.data;
  },
};
