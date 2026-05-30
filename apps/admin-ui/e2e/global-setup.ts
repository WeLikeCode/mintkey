/**
 * Global setup — log in once via Keycloak OIDC and persist session state.
 *
 * Creates state.json that all test workers reuse, avoiding repeated logins.
 *
 * Flow:
 *  1. Navigate to ${BASE_URL}/auth/start  → 302 → Keycloak auth page
 *  2. Fill #username / #password, click #kc-login
 *  3. Keycloak → admin-api /v1/auth/oidc/callback → sets mintkey_session + csrf_token
 *  4. Wait for redirect back to ${BASE_URL}/admin
 *  5. Save storageState to e2e/state.json
 */

import { chromium } from "@playwright/test";
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
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  try {
    // Step 1 — start OIDC flow; admin-ui proxies to admin-api which 302s to Keycloak
    await page.goto(`${BASE_URL}/auth/start`, { waitUntil: "domcontentloaded" });

    // Step 2 — we are now on the Keycloak login page
    // Wait for #username field (Keycloak standard theme)
    await page.waitForSelector("#username", { timeout: 30_000 });
    await page.fill("#username", USER_EMAIL);
    await page.fill("#password", USER_PASS);
    await page.click("#kc-login");

    // Step 3 — Keycloak POSTs credentials and 302s back through the OIDC callback,
    // which sets mintkey_session + csrf_token cookies and 302s to /admin.
    await page.waitForURL(
      (url) => url.href.includes("/admin") && !url.href.includes("/auth/"),
      { timeout: 30_000 },
    );

    // Step 4 — save storage state (cookies + localStorage) to disk
    const statePath = path.resolve(__dirname, "state.json");
    await context.storageState({ path: statePath });
    console.log("Global setup — OIDC login succeeded; state saved to", statePath);
  } catch (err) {
    console.error("Global setup FAILED — tests will run unauthenticated:", err);
    // Do not rethrow: allow tests to run (they may skip themselves when unauthenticated)
  } finally {
    await browser.close();
  }
}