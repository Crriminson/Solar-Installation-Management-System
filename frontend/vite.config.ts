// Vite configuration.
//
// Development proxies /api to the Django server so the browser sees one
// origin, matching the deployment layout described in spec.md section 3.

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://127.0.0.1:8000";
const DEV_PORT = 5173;

export default defineConfig({
  plugins: [react()],
  server: {
    port: DEV_PORT,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/admin": { target: API_TARGET, changeOrigin: true },
    },
  },
});
