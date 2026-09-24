import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend (backend/main.py, FastAPI) is expected on :8000. In dev, /api is
// proxied there so the browser never needs CORS. Override with VITE_API_PROXY.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // three.js (~550 kB) changes rarely: its own long-cached chunk.
        manualChunks: { three: ["three"], react: ["react", "react-dom", "react-router-dom"] },
      },
    },
    chunkSizeWarningLimit: 650,
  },
});
