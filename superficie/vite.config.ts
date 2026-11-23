import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { assistantPlugin } from "./assistant/vite-plugin";

// En desarrollo, /sldb se redirige al `sldb serve` y /desk a la vista HTTP de deskops.
const sldbTarget = process.env.SLDB_TARGET ?? "http://127.0.0.1:8085";
const deskTarget = process.env.DESK_TARGET ?? "http://127.0.0.1:8091";

export default defineConfig(({ command }) => ({
  // Compilada, la superficie es la wiki de `tutor web`: se sirve bajo /wiki/ y queda dentro del paquete
  // (src/tutor/static/wiki, versionada: quien usa el tutor no tiene Node). En `vite dev`, en la raíz.
  base: process.env.SUPERFICIE_BASE ?? (command === "build" ? "/wiki/" : "/"),
  // El asistente (solo en `vite dev`) edita el mismo store que sirve `sldb serve`.
  plugins: [react(), assistantPlugin({ sldbTarget })],
  build: {
    outDir: process.env.SUPERFICIE_OUT ?? "../src/tutor/static/wiki",
    emptyOutDir: true,
    rollupOptions: { input: { main: "index.html" } },
  },
  server: {
    proxy: {
      "/sldb": { target: sldbTarget, changeOrigin: true, rewrite: (path) => path.replace(/^\/sldb/, "") },
      "/desk": { target: deskTarget, changeOrigin: true, rewrite: (path) => path.replace(/^\/desk/, "") },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
}));
