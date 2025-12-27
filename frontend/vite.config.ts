import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Default to Docker internal DNS, override with env var for local dev
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://api:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
