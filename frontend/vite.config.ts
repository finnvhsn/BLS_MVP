import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Entwicklung: Backend läuft auf :8000 (im Betrieb serviert FastAPI den Build)
      "/api": "http://localhost:8000",
    },
  },
});
