import { api } from "@/lib/apiClient";
import { UserResponse } from "@/features/auth/api/auth";

export const usersApi = {
  regenerateApiKey: async () => {
    const response = await api.post<UserResponse>("/v1/users/me/api-key");
    return response.data;
  },
};
