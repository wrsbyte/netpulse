import { defineConfig, devices } from '@playwright/test'

// E2E against the running netpulse-api (which serves the built SPA on :8477). Start it first:
//   systemctl --user start netpulse-api   (or `make run`)
// then: pnpm test:e2e
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  // The dev API is a single uvicorn worker; a page fires ~16 concurrent queries, so a cold-start
  // assertion can transiently exceed its timeout under the burst. One retry absorbs that without
  // masking a real break (which fails both attempts).
  retries: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.NETPULSE_URL ?? 'http://127.0.0.1:8477',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
