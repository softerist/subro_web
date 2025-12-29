import axios from "axios";
import { useAuthStore } from "@/store/authStore";

// Create base instance
export const api = axios.create({
  baseURL: "/api", // Caddy will proxy this to the backend
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
});

let refreshPromise: Promise<string | null> | null = null;

const refreshAccessToken = async () => {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const refreshResponse = await api.post("/v1/auth/refresh");
        const newAccessToken = refreshResponse.data.access_token ?? null;
        if (newAccessToken) {
          useAuthStore.getState().setAccessToken(newAccessToken);
        }
        return newAccessToken;
      } catch (err) {
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }

  return refreshPromise;
};

// Request interceptor: attach Access Token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  const isRefreshRequest = config.url?.includes("/v1/auth/refresh");
  if (token && !isRefreshRequest) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: handle 401 and refresh token
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (!originalRequest) {
      return Promise.reject(error);
    }

    // Detect 401 error and ensure we haven't already tried to refresh
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (originalRequest.url?.includes("/v1/auth/refresh")) {
        return Promise.reject(error);
      }
      originalRequest._retry = true;

      try {
        const newAccessToken = await refreshAccessToken();
        if (newAccessToken) {
          originalRequest.headers = originalRequest.headers ?? {};
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return api(originalRequest);
        }
        throw new Error("Refresh did not return a new access token.");
      } catch (refreshError) {
        // Refresh failed (token expired or invalid)
        useAuthStore.getState().logout(); // Clear state
        // Redirect to login page
        if (
          window.location.pathname !== "/login" &&
          window.location.pathname !== "/setup"
        ) {
          window.location.href = "/login";
        }
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  },
);
