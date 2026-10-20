import { defineConfig, devices } from '@playwright/test';

/**
 * Zwei Server: die API (`roboprint serve`, Läufe aus `../runs`, also `runs/verify/S1` →
 * run_id `verify/S1`) und Vite (leitet `/api` an Port 8765 weiter). Die Befehle laufen im
 * Ordner `web/`. Python kann über ROBOPRINT_PYTHON umgestellt werden.
 */
const python = process.env.ROBOPRINT_PYTHON ?? '/opt/fgc-venv/bin/python';

export default defineConfig({
  testDir: 'e2e',
  outputDir: 'test-results',
  timeout: 120_000,
  use: { baseURL: 'http://127.0.0.1:5173' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${python} -m roboprint serve --port 8765 --runs ../runs`,
      env: { PYTHONPATH: '../core/src' },
      url: 'http://127.0.0.1:8765/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
