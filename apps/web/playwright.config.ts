import { defineConfig, type PlaywrightTestConfig } from "@playwright/test";

/**
 * Playwright E2E configuration.
 *
 * Environments (all started automatically, isolated from dev previews):
 * - demo : API :8100 (AUTH_MODE=demo)  + web :3100 — the default journey.
 * - auth : API :8101 (AUTH_MODE=required, bootstrap admin, malware scan
 *          enforcing with an unreachable clamd host so uploads fail closed)
 *          + web :3200 — login/logout/unauthorised/fail-closed-scan flows.
 *
 * The chromium binary is resolved from CHROMIUM_PATH when the Playwright
 * browser CDN is unavailable (sandboxed environments); otherwise stock
 * Playwright browsers are used.
 */

const API_DEMO = 8100;
const API_AUTH = 8101;
const WEB_DEMO = 3100;
const WEB_AUTH = 3200;

const apiEnv = (port: number, extra: Record<string, string> = {}) => ({
  ...process.env,
  DATABASE_URL: `sqlite:////tmp/shramai-e2e-${port}/shramai.db`,
  STORAGE_DIR: `/tmp/shramai-e2e-${port}/storage`,
  APP_ENV: "demo",
  AUTH_MODE: "demo",
  KNOWLEDGE_DIR: "data/knowledge",
  RATE_LIMIT_ENABLED: "false",
  MAX_UPLOAD_MB: "1",
  // The web server proxies API calls (Host = proxy target), so the browser
  // web origin must be in the explicit allow-list (same as any proxied
  // production deployment).
  ALLOWED_ORIGINS: "http://127.0.0.1:3100,http://127.0.0.1:3200",
  ...extra,
});

const executablePath = process.env.CHROMIUM_PATH
  ? { executablePath: process.env.CHROMIUM_PATH }
  : {};

const config: PlaywrightTestConfig = defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  outputDir: "e2e-artifacts",
  use: {
    baseURL: `http://127.0.0.1:${WEB_DEMO}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    launchOptions: {
      ...executablePath,
      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    },
  },
  projects: [
    {
      name: "demo-desktop",
      testIgnore: /smoke-mobile|auth\.spec/,
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: "demo-mobile",
      testMatch: /smoke-mobile\.spec\.ts/,
      use: { viewport: { width: 390, height: 844 } },
    },
    {
      name: "auth",
      testMatch: /auth\.spec\.ts/,
      use: {
        baseURL: `http://127.0.0.1:${WEB_AUTH}`,
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
  webServer: [
    {
      name: "api-demo",
      command: "mkdir -p /tmp/shramai-e2e-8100 && rm -rf /tmp/shramai-e2e-8100/* ../api/storage/* 2>/dev/null; ../api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100",
      cwd: "../api",
      url: `http://127.0.0.1:${API_DEMO}/api/v1/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: apiEnv(API_DEMO),
    },
    {
      name: "api-auth",
      command:
        "mkdir -p /tmp/shramai-e2e-8101 && rm -rf /tmp/shramai-e2e-8101/* 2>/dev/null; ../api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8101",
      cwd: "../api",
      url: `http://127.0.0.1:${API_AUTH}/api/v1/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: apiEnv(API_AUTH, {
        AUTH_MODE: "required",
        MALWARE_SCAN_MODE: "enforcing",
        CLAMD_HOST: "127.0.0.1",
        CLAMD_PORT: "9", // unreachable: uploads must fail closed
        BOOTSTRAP_ADMIN_EMAIL: "admin@e2e.example.com",
        BOOTSTRAP_ADMIN_NAME: "E2E Admin",
        BOOTSTRAP_ADMIN_PASSWORD: "e2e-admin-password-1",
      }),
    },
    {
      name: "web-demo",
      command: `npx next start -p ${WEB_DEMO}`,
      cwd: ".",
      url: `http://127.0.0.1:${WEB_DEMO}/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: { ...process.env, API_ORIGIN: `http://127.0.0.1:${API_DEMO}` },
    },
    {
      name: "web-auth",
      command: `npx next start -p ${WEB_AUTH}`,
      cwd: ".",
      url: `http://127.0.0.1:${WEB_AUTH}/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: { ...process.env, API_ORIGIN: `http://127.0.0.1:${API_AUTH}` },
    },
  ],
});

export default config;
