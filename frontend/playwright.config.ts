import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E configuration (smoke tests).
 *
 * NOTE: Additive to the existing Vitest unit-test setup — does not touch it.
 * - Tests live in `./e2e` (Vitest still picks up `src/**` unit tests).
 * - `webServer` boots `npm run dev` (Vite) on port 3000 and reuses it if
 *   already running, so local iteration is fast.
 * - `baseURL` is 3000 because `vite.config.ts` pins the dev server to 3000.
 *   (The task spec said 5173, but this project overrides Vite's default.)
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,
  expect: { timeout: 5_000 },

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
