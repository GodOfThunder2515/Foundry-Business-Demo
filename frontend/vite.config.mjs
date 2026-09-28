import { resolve } from "node:path";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const envDir = resolve(process.cwd(), "..");

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, "");
  const endpoint = env.FUNCTION_URL ? new URL(env.FUNCTION_URL) : null;

  return {
    envDir,
    build: {
      outDir: "dist/client",
    },
    optimizeDeps: {
      include: ["react", "react-dom/client"],
    },
    server: {
      host: "0.0.0.0",
      allowedHosts: ["terminal.local"],
      warmup: {
        clientFiles: ["./src/main.jsx"],
      },
      proxy: endpoint
        ? {
            "/api/chat": {
              target: endpoint.origin,
              changeOrigin: true,
              rewrite: () => `${endpoint.pathname}${endpoint.search}`,
              headers: env.FUNCTION_KEY ? { "x-functions-key": env.FUNCTION_KEY } : {},
            },
          }
        : undefined,
    },
    plugins: [react()],
  };
});
