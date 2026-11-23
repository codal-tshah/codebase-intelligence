/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Unit tests only; browser E2E specs in e2e/ run with Playwright (`npm run test:e2e`).
  test: { exclude: ["e2e/**", "node_modules/**", "dist/**"] },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Point the dev UI at another backend with CI_API_URL=http://127.0.0.1:8010 npm run dev
        target: process.env.CI_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
