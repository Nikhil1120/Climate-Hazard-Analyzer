import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/Climate-Hazard-Analyzer/" : "/",
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
}));