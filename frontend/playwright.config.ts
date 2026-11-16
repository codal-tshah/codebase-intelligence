import { defineConfig } from "@playwright/test";

/**
 * Browser E2E + accessibility checks. Uses the installed Chrome (`channel: "chrome"`), so no
 * browser download is needed locally or on GitHub's ubuntu runners. Reuses servers that are
 * already running (dev workflow); in CI it starts the API and the Vite dev server itself.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "e2e",
  testMatch: /.*\.spec\.ts/,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL,
    channel: "chrome",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : [
        {
          command: "uv run ci serve --port 8000",
          cwd: "../backend",
          url: "http://127.0.0.1:8000/health",
          reuseExistingServer: true,
          timeout: 120_000,
        },
        {
          command: "npm run dev",
          url: "http://localhost:5173",
          reuseExistingServer: true,
          timeout: 60_000,
        },
      ],
});
