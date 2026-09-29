import { Agent } from "node:https";
import { resolve } from "node:path";
import tls from "node:tls";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const envDir = resolve(process.cwd(), "..");

// Trust the OS certificate store as well as Node's bundled CAs, so the dev
// proxy still works when antivirus or a corporate proxy re-signs HTTPS traffic
// with a locally installed root (browsers already trust that store).
function systemTrustAgent() {
  if (typeof tls.getCACertificates !== "function") return undefined;
  try {
    return new Agent({
      keepAlive: true,
      ca: [...tls.getCACertificates("default"), ...tls.getCACertificates("system")],
    });
  } catch {
    return undefined;
  }
}

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
              agent: endpoint.protocol === "https:" ? systemTrustAgent() : undefined,
              rewrite: () => `${endpoint.pathname}${endpoint.search}`,
              headers: env.FUNCTION_KEY ? { "x-functions-key": env.FUNCTION_KEY } : {},
            },
          }
        : undefined,
    },
    plugins: [react()],
  };
});
