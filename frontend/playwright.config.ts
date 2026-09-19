import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: '../output/playwright/results',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5175',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npx vite --config tests/e2e/vite.config.ts --host 127.0.0.1 --port 5175 --strictPort',
    url: 'http://127.0.0.1:5175/tests/e2e/index.html',
    reuseExistingServer: false,
    timeout: 30_000,
  },
})
