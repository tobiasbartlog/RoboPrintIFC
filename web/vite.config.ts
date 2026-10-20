/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';
import { devAssets } from './vite-dev-assets';

export default defineConfig({
  plugins: [react(), devAssets()],
  build: {
    rollupOptions: {
      input: { main: resolve(__dirname, 'index.html'), 'scene-test': resolve(__dirname, 'scene-test.html') },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test-setup.ts'],
    // Ganze App-Abläufe unter Last (parallele Agenten auf 4 vCPU): 5 s reichen nicht verlässlich.
    testTimeout: 30_000,
  },
});
