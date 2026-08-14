import { defineConfig, devices } from '@playwright/test'

// E2E against the running netpulse-api (which serves the built SPA on :8477). Start it first:
//   systemctl --user start netpulse-api   (or `make run`)
// then: pnpm test:e2e
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.NETPULSE_URL ?? 'http://127.0.0.1:8477',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
