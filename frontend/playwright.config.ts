import { defineConfig } from '@playwright/test'

/**
 * End-to-end tests against the real stack: Vite dev server → FastAPI → PostgreSQL.
 * Start the backend first with EMAIL_BACKEND=console and its log written to $BACKEND_LOG,
 * so tests can read verification/reset links (no real email is sent).
 */
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 45_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { channel: process.env.PW_CHANNEL || undefined, baseURL: 'http://localhost:5173', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: {
    command: 'npm run dev -- --strictPort',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
