import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Use 8001 in dev — port 8000 is often grabbed by other local services.
      // Override via env var if you want to point at a different backend.
      "/api":    { target: process.env.DAMOCLES_BACKEND || "http://localhost:8001", changeOrigin: true },
      "/static": { target: process.env.DAMOCLES_BACKEND || "http://localhost:8001", changeOrigin: true },
      "/ws":     { target: (process.env.DAMOCLES_BACKEND || "http://localhost:8001").replace("http","ws"), ws: true },
      // /health is the FastAPI liveness probe — proxied so the SystemPill,
      // AuditLog (demo-mode gate), and any other client-side health
      // consumer can reach it from the dev frontend. Without this, Vite
      // returns the SPA index.html for /health and React-Query parses
      // the HTML as JSON, silently leaving health undefined.
      "/health": { target: process.env.DAMOCLES_BACKEND || "http://localhost:8001", changeOrigin: true },
      // /landing is the marketing/static frontend hosted by FastAPI under
      // /landing/. Proxied in dev so the topbar "← landing" link works
      // without a second Vite server.
      "/landing": { target: process.env.DAMOCLES_BACKEND || "http://localhost:8001", changeOrigin: true },
    },
  },
});
