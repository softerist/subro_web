import { api } from "@/lib/apiClient";

export interface HealthCheckResponse {
  status: string;
  // Add other health check fields if known (e.g. database: "ok")
  [key: string]: unknown;
}

export interface DbUserTestResponse {
  status: string;
  first_user_email?: string;
}

export const systemApi = {
  // Health Check
  getHealth: async () => {
    const response = await api.get<HealthCheckResponse>("/v1/healthz");
    return response.data;
  },

  // Debug: Test DB User Access
  testDbUsers: async () => {
    const response = await api.get<DbUserTestResponse>("/v1/test-db-users");
    return response.data;
  },
};
