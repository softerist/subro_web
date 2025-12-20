import axios from "axios";
import { useAuthStore } from "@/store/authStore";

// Create base instance
export const api = axios.create({
  baseURL: "/api", // Caddy will proxy this to the backend
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor: attach Access Token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: handle 401 and refresh token
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Detect 401 error and ensure we haven't already tried to refresh
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Attempt to refresh (cookie based, so no args needed usually if cookie is HttpOnly)
        // If your backend refresh endpoint needs a body or header, add it here.
        // Assuming /auth/refresh endpoint uses the cookie.
        await api.post("/v1/auth/refresh");

        // If successful, the browser will have updated the cookie (if it returned a new cookie)
        // But importantly, we might need a new Access Token if the backend returns one in the body.
        // If the backend returns { access_token: "..." }, capture it.
        // For fastapi-users (cookie transport for refresh), it usually sets a cookie.
        // If using Bearer for access, we need the new access token.

        // WAIT: The plan says "Refresh Token: Longer-lived ... sent as HttpOnly cookie".
        // "Access Token ... sent in response body".
        // So /refresh should return { access_token: "new_token", token_type: "bearer" }.

        // Let's assume the response has data.
        // But wait, axios interceptor using the same 'api' instance might cycle if /refresh also 401s.
        // We should skip the interceptor for the refresh call or be careful.
        // 'api' has the interceptor attached.
        // If /refresh fails with 401, it will loop if we are not careful.
        // However, originalRequest._retry = true prevents the loop for the *original* request.
        // If /refresh itself fails, it rejects.

        const refreshResponse = await axios.post(
          "/api/v1/auth/refresh",
          {},
          { withCredentials: true },
        );

        const newAccessToken = refreshResponse.data.access_token;
        if (newAccessToken) {
          useAuthStore.getState().setAccessToken(newAccessToken);
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return api(originalRequest);
        }
      } catch (refreshError) {
        // Refresh failed (token expired or invalid)
        useAuthStore.getState().logout(); // Clear state
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  },
);
