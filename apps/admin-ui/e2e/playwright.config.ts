/**
 * Playwright E2E config — Mintkey AdminJS UI tests.
 *
 * Source of truth: docs/architecture/03-flows/
 * Tests derive from: F-OP-01 → F-OP-04, T-1.1.4 → T-1.12.4, S-SEC-1.
 */

import { defineConfig, devices } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import { config as loadDotenv } from "dotenv";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load .env.local if present (local developer overrides, not committed)
loadDotenv({ path: path.resolve(__dirname, ".env.local"), override: false });

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8081";
const USER_PASS = process.env.PLAYWRIGHT_PASS ?? "";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["junit", { outputFile: "test-results/junit.xml" }],
    ["list"],
  ],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ignoreHTTPSErrors: !!process.env.PLAYWRIGHT_IGNORE_TLS,
    storageState: USER_PASS ? path.resolve(__dirname, "state.json") : undefined,
    navigationTimeout: 30_000,
    timeout: 30_000,
  },
  globalSetup: path.resolve(__dirname, "global-setup.ts"),
  globalTeardown: path.resolve(__dirname, "global-teardown.ts"),
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});