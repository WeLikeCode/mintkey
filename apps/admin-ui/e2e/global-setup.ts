/**
 * Global setup — log in once via Keycloak OIDC and persist session state.
 *
 * Drives the real production login path (SSO-C / ADR-0019):
 *   browser → /auth/start → admin-api /v1/auth/oidc/login → Keycloak →
 *   admin-api /v1/auth/oidc/callback → mintkey_session cookie → redirect to /admin
 *
 * Creates a state.json that all test workers reuse, avoiding repeated logins.
 * If PLAYWRIGHT_PASS is empty, writes no state and emits a warning so tests
 * that depend on auth will fail visibly rather than silently.
 *
 * Source: ADR-0019 §3; fix/playwright-e2e-auth-fixture 03-investigation-report.md
 */

import { chromium } from "@playwright/test";
import * as fs from "fs";
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

/** Resolved path to the storageState file — must match playwright.config.ts */
const STATE_PATH = path.resolve(__dirname, "state.json");

export default async function globalSetup() {
  if (!USER_PASS) {
    console.warn(
      "[global-setup] PLAYWRIGHT_PASS empty — running without auth; resource tests will fail"
    );
    return;
  }

  console.log(`[global-setup] Starting OIDC login for ${USER_EMAIL} against ${BASE_URL}`);

  const browser = await chromium.launch();

  try {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();

    try {
      // -----------------------------------------------------------------------
      // Step (a): Navigate to /auth/start — admin-ui issues 302 to
      //           admin-api /v1/auth/oidc/login which issues 302 to Keycloak.
      // -----------------------------------------------------------------------
      console.log(`[global-setup] Navigating to ${BASE_URL}/auth/start`);
      await page.goto(`${BASE_URL}/auth/start`, { waitUntil: "load" });

      console.log(`[global-setup] Landed at: ${page.url()}`);

      // -----------------------------------------------------------------------
      // Step (b): Wait for Keycloak's login form.
      //
      // Standard Keycloak 24+ login form has:
      //   <input id="username" name="username" ...>  (or id="email" in some themes)
      //   <input id="password" name="password" ...>
      //   <button name="login" ...>Sign In</button>
      //
      // Keycloak's PatternFly theme also renders a "Show password" toggle button
      // with aria-label="Show password", so getByLabel(/password/i) would match
      // both the input and the toggle. Use the input[type=password] CSS selector
      // as the most reliable cross-theme approach.
      // -----------------------------------------------------------------------
      console.log("[global-setup] Waiting for Keycloak login form …");
      const usernameField = page.locator("input#username, input#email, input[name=username], input[name=email]").first();
      const passwordField = page.locator("input#password, input[name=password], input[type=password]").first();
      await usernameField.waitFor({ state: "visible", timeout: 30_000 });

      console.log(`[global-setup] Keycloak form found. Filling credentials for ${USER_EMAIL}`);
      await usernameField.fill(USER_EMAIL);
      await passwordField.fill(USER_PASS);

      // -----------------------------------------------------------------------
      // Step (c): Submit the Keycloak login form.
      //
      // Keycloak's primary submit is <button name="login"> but themes may
      // vary; fall back to input[type=submit] and any button[type=submit].
      // -----------------------------------------------------------------------
      const submitBtn = page
        .locator('button[name="login"], input[type="submit"], button[type="submit"]')
        .first();

      console.log("[global-setup] Submitting Keycloak login form …");
      await Promise.all([
        page.waitForURL(/\/admin(\/|$)/, { timeout: 30_000 }),
        submitBtn.click(),
      ]);

      console.log(`[global-setup] Post-login URL: ${page.url()}`);

      // -----------------------------------------------------------------------
      // Step (d): Save storageState.
      //
      // mintkey_session is set by admin-api (:8080) with no explicit Domain
      // attribute. Per RFC 6265, cookies without Domain are host-only but
      // browsers treat "localhost" cookies as port-agnostic, so the cookie is
      // visible to admin-ui (:8081) as well. Admin-ui validates sessions via an
      // internal HTTP call to admin-api /v1/auth/whoami, forwarding the cookie
      // from the browser request — so the storageState only needs the cookie
      // to be present for localhost.
      // -----------------------------------------------------------------------
      const state = await ctx.storageState();
      const cookieSummary = state.cookies
        .map((c) => `${c.name}@${c.domain}${c.path}`)
        .join(", ");
      console.log(`[global-setup] storageState cookies: ${cookieSummary}`);

      await ctx.storageState({ path: STATE_PATH });
      console.log(`[global-setup] ✅ saved storageState to ${STATE_PATH}`);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      const stack = err instanceof Error ? err.stack ?? "" : "";
      console.error(`[global-setup] ❌ OIDC login failed: ${errMsg}\n${stack}`);

      // Delete any stale/partial state.json so tests don't try to use it.
      try {
        if (fs.existsSync(STATE_PATH)) {
          fs.unlinkSync(STATE_PATH);
          console.warn(`[global-setup] Deleted stale ${STATE_PATH} after login failure`);
        }
      } catch (cleanupErr) {
        console.warn(`[global-setup] Could not delete stale state.json: ${cleanupErr}`);
      }

      // Fall through — don't rethrow. Tests will run unauthenticated, which
      // mirrors the existing behaviour when PLAYWRIGHT_PASS is empty.
    } finally {
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
}
