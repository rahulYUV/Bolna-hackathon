import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/static/",
  envDir: "..",
  server: {
    proxy: {
      "/customers": "http://127.0.0.1:8000",
      "/calls": "http://127.0.0.1:8000",
      "/auth": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "../app/static",
    emptyOutDir: true,
  },
});
