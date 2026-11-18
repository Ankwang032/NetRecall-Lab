import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// npm run dev 중에는 API 요청을 FastAPI(uvicorn)로 넘긴다
const backend = "http://127.0.0.1:8000";
const apiPaths = ["/health", "/sync", "/concepts", "/reviews", "/cards", "/questions"];

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: { proxy: Object.fromEntries(apiPaths.map((p) => [p, backend])) },
  test: { environment: "jsdom", setupFiles: ["src/test-setup.ts"] },
});
