/// <reference types="vitest" />
import { defineConfig } from "vite";

export default defineConfig({
  // relative Pfade, damit der Build als statischer Ordner überall läuft
  base: "./",
  server: {
    fs: {
      // erlaubt im Dev-Modus das Laden von Laufordnern aus dem Monorepo
      // via /@fs/-URLs (?run=...), z. B. runs/<lauf>/
      allow: [".."],
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
