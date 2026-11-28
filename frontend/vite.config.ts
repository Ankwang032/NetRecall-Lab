import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// npm run dev 중에는 API 요청을 FastAPI(uvicorn)로 넘긴다
const backend = "http://127.0.0.1:8000";
const apiPaths = ["/health", "/sync", "/concepts", "/reviews", "/cards", "/questions", "/labs", "/lab-runs", "/dashboard"];

// 화면 경로(/labs 등)는 API 경로와 겹친다. 주소창으로 연 요청(Accept: text/html)은 넘기지 않고 화면을 준다
const proxy = {
  target: backend,
  ws: true, // 실습 웹 터미널 (/lab-runs/{id}/terminal)
  bypass: (req: { headers: { accept?: string } }) => (req.headers.accept?.includes("text/html") ? "/index.html" : undefined),
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: { proxy: Object.fromEntries(apiPaths.map((p) => [p, proxy])) },
  test: { environment: "jsdom", setupFiles: ["src/test-setup.ts"] },
});
