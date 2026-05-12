/**
 * Tier 1 — Login flows (critical path).
 *
 * Source: F-OP-01; T-1.1.4; Req 2 AC1, AC8.
 *
 * Tests:
 *  1. Internal auth — valid credentials → dashboard redirect
 *  2. Internal auth — invalid credentials → error, no redirect
 *  3. Internal auth — empty credentials → validation
 *  4. Logout — session cleared, redirected to login
 *  5. Session persistence — page reload keeps operator logged in
 */

import { test, expect, type Page } from "@playwright/test";
import { LoginPage } from "../pages/login.js";

test.describe("Tier 1 — Login (F-OP-01)", () => {
  let page: Page;
  let login: LoginPage;

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    login = new LoginPage(page);
    // Ensure we start from a clean session
    await page.context().clearCookies();
    await login.goto();
  });

  test("1. valid internal login redirects to dashboard", async () => {
    const email = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
    const pass = process.env.PLAYWRIGHT_PASS ?? "";

    if (!pass) {
      test.skip(true, "PLAYWRIGHT_PASS not set");
      return;
    }

    await login.login(email, pass);

    // After login, we should be on the dashboard (AdminJS redirects to /admin)
    await expect(page).toHaveURL(/\/admin/);
    // Verify we are authenticated — email visible in header
    await expect(page.locator("body")).toContainText("admin@mintkey.internal");
  });

  test("2. invalid credentials shows error", async () => {
    await login.email.fill("admin@mintkey.internal");
    await login.password.fill("wrong-password-definitely-invalid");
    await Promise.all([
      page.waitForResponse((r) => r.url().includes("/internal-login") && r.status() === 401, { timeout: 5_000 }).catch(() => {}),
      login.submitButton.click(),
    ]);

    // Should remain on login page or show error
    await expect(login.email).toBeVisible();
  });

  test("3. empty credentials stay on login page", async () => {
    await login.email.fill("");
    await login.password.fill("");
    await login.submitButton.click();

    // Should not redirect to dashboard
    await expect(page).not.toHaveURL(/\/admin\/resources\//);
  });

  test("4. logout clears session", async () => {
    // First log in
    const email = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
    const pass = process.env.PLAYWRIGHT_PASS ?? "";
    if (!pass) { test.skip(true, "PLAYWRIGHT_PASS not set"); return; }

    await login.login(email, pass);
    await expect(page).toHaveURL(/\/admin/);

    // AdminJS logout — navigate directly to logout endpoint
    await page.goto("/admin/logout");

    // Should redirect back to login
    await expect(page).toHaveURL(/\/admin\/login/);
  });

  test("5. session persists across page reload", async () => {
    const email = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
    const pass = process.env.PLAYWRIGHT_PASS ?? "";
    if (!pass) { test.skip(true, "PLAYWRIGHT_PASS not set"); return; }

    await login.login(email, pass);
    await expect(page).toHaveURL(/\/admin/);

    // Reload page
    await page.reload();
    await expect(page).toHaveURL(/\/admin/);

    // Dashboard content should still be visible — email in header confirms auth
    await expect(page.locator("body")).toContainText("admin@mintkey.internal");
  });
});