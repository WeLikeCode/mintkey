/**
 * Minimal Playwright config for the admin-UI smoke test (`tests/e2e/smoke.spec.ts`).
 *
 * Runs against the live `docker compose` stack (admin-ui at :8081), with no
 * global setup / teardown — the smoke spec logs in itself, reading the bootstrap
 * password from `process.env.MINTKEY_ADMIN_PASSWORD`. The richer onboarding
 * suite lives under `e2e/` with its own config; this one is deliberately
 * standalone so a single `npx playwright test tests/e2e/smoke.spec.ts` works.
 *
 * Source: team/remediation/ADMIN_UI_SPEC.md §2.1 (the dashboard), §4 (browser test).
 */

import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.MINTKEY_ADMIN_UI_URL ?? "http://localhost:8081";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    navigationTimeout: 30_000,
    actionTimeout: 15_000,
  },
  timeout: 180_000,
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
