/**
 * Global setup — log in once and persist session state.
 *
 * Creates a storageState.json that all test workers reuse,
 * avoiding repeated logins and reducing test time.
 */

import { chromium, type BrowserContext } from "@playwright/test";
import * as process from "process";
import * as path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const env = process.env as any;

const BASE_URL = env.PLAYWRIGHT_BASE_URL ?? "http://localhost:8081";
const USER_EMAIL = env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
const USER_PASS = env.PLAYWRIGHT_PASS ?? "";

export default async function globalSetup() {
  if (!USER_PASS) {
    console.warn("PLAYWRIGHT_PASS not set — skipping global login. Tests must set storageState themselves.");
    return;
  }

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // Navigate to AdminJS login page
    await page.goto(`${BASE_URL}/admin/login`, { waitUntil: "networkidle" });

    // AdminJS renders login form via React bundles — wait for input[name=email]
    await page.waitForSelector("input[type=email], input[name=email]", { timeout: 15_000 });
    await page.locator("input[type=email], input[name=email]").first().fill(USER_EMAIL);
    await page.locator("input[type=password], input[name=password]").first().fill(USER_PASS);
    await page.getByRole("button", { name: /sign in|login/i }).click();

    // AdminJS redirects to /admin after successful login
    await page.waitForURL(/\/admin/, { timeout: 15_000 });

    // Save storage state — must match path in playwright.config.ts
    const statePath = path.resolve(__dirname, "state.json");
    await context.storageState({ path: statePath });
    console.log("✅ Global setup — login state saved to", statePath);
  } catch (err) {
    console.error("⚠️  Global setup failed — tests will run unauthenticated:", err);
  } finally {
    await browser.close();
  }
}