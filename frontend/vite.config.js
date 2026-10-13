import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api to the FastAPI server so no CORS setup is needed.
export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "https://climate-hazard-analyzer-j55f.onrender.com" } },
});
