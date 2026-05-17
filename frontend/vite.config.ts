import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Use 8000 in dev — matches the backend start script and docs.
      // Override via env var `DAMOCLES_BACKEND` if you need a different backend.
      "/api":    { target: process.env.DAMOCLES_BACKEND || "http://localhost:8000", changeOrigin: true },
      "/static": { target: process.env.DAMOCLES_BACKEND || "http://localhost:8000", changeOrigin: true },
      "/ws":     { target: (process.env.DAMOCLES_BACKEND || "http://localhost:8000").replace("http","ws"), ws: true },
      // /health is the FastAPI liveness probe — proxied so the SystemPill,
      // AuditLog (demo-mode gate), and any other client-side health
      // consumer can reach it from the dev frontend. Without this, Vite
      // returns the SPA index.html for /health and React-Query parses
      // the HTML as JSON, silently leaving health undefined.
      "/health": { target: process.env.DAMOCLES_BACKEND || "http://localhost:8000", changeOrigin: true },
      // /landing is the marketing/static frontend hosted by FastAPI under
      // /landing/. Proxied in dev so the topbar "← landing" link works
      // without a second Vite server.
      "/landing": { target: process.env.DAMOCLES_BACKEND || "http://localhost:8000", changeOrigin: true },
    },
  },
});
