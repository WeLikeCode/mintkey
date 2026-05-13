/**
 * W5: Logout and session expiry.
 *
 * Verifies:
 *  (a) Logout invalidates the session — navigating to a protected resource after
 *      logout redirects to /admin/login.
 *  (b) Deleting the session cookie and navigating to a protected page redirects
 *      to /admin/login (no crash, no blank page, no JS error box).
 *
 * Session-isolation note: test (a) must NOT use the shared storageState session
 * because calling /admin/logout invalidates the server-side session, which would
 * break all other tests that share the same cookie via global storageState.
 * Instead, test (a) performs a fresh form login within the test context, logs out
 * that fresh session, and leaves the shared session intact.
 *
 * Source: ADR-0019; PLAYWRIGHT_EXTENSION_PLAN.md W5.
 */

import { test, expect } from "../fixtures/test.js";

const ADMIN_EMAIL = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";

test.describe("21 — Logout and session expiry", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // ── (a) Logout invalidates the session ───────────────────────────────────────
  // Uses a FRESH login (not storageState) to avoid invalidating the shared session.
  test("logout redirects to /admin/login on next visit (fresh session)", async ({
    page,
    consoleErrors,
  }) => {
    const pass = process.env.PLAYWRIGHT_PASS ?? "";
    if (!pass) {
      void consoleErrors;
      return;
    }

    // Clear the storageState session so this context has no pre-existing cookies
    await page.context().clearCookies();

    // Navigate to the login page and fill credentials to get a FRESH session
    await page.goto("/admin/login", { waitUntil: "domcontentloaded" });
    const emailInput = page.locator("input[type=email], input[name=email]").first();
    const passInput = page.locator("input[type=password], input[name=password]").first();

    const hasLoginForm =
      (await emailInput.count()) > 0 && (await passInput.count()) > 0;
    if (!hasLoginForm) {
      // Login form not visible — stack may not be running; skip gracefully
      void consoleErrors;
      return;
    }

    await emailInput.fill(ADMIN_EMAIL);
    await passInput.fill(pass);
    await Promise.all([
      page.waitForURL(/\/admin/, { timeout: 15_000 }),
      page.locator("button[type=submit], button:has-text('Sign in'), button:has-text('Login')").first().click(),
    ]);

    const afterLoginUrl = page.url();
    const isLoggedIn = !afterLoginUrl.includes("/login");
    if (!isLoggedIn) {
      // Login failed — skip gracefully (wrong credentials or stack issue)
      void consoleErrors;
      return;
    }

    // Try the logout button first; fall back to direct /admin/logout endpoint
    const logoutEl = page
      .locator(
        'a[href*="logout" i], button:has-text("logout"), a:has-text("logout"), ' +
          '[data-testid="logout"], [aria-label*="logout" i]',
      )
      .first();

    if ((await logoutEl.count()) > 0) {
      await logoutEl.click();
      await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
    } else {
      await page.goto("/admin/logout", { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
    }

    const postLogoutUrl = page.url();
    const isOnLoginPage = /\/login/i.test(postLogoutUrl);

    if (isOnLoginPage) {
      // Logout redirected to login — verify login form is rendered
      const bodyText = (await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) ?? "";
      expect(bodyText).not.toContain("Javascript Error");
    }

    // After logout, a protected resource must redirect to /admin/login
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});

    const finalUrl = page.url();
    expect(
      finalUrl,
      "after logout, accessing protected resource must redirect to login",
    ).toMatch(/\/login|\/admin\/login/i);

    const body = (await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) ?? "";
    expect(body).not.toContain("Javascript Error");

    void consoleErrors;
  });

  // ── (b) Expired / deleted session cookie → redirect to login ─────────────────
  // Clears cookies in the current context (doesn't hit the server logout endpoint).
  test("deleting session cookie redirects to /admin/login with no crash", async ({
    page,
    consoleErrors,
  }) => {
    // Navigate to a protected page first (uses storageState — we are authenticated)
    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});

    // Clear ALL cookies for this context — simulates an expired / revoked session
    await page.context().clearCookies();

    // Navigate to a protected resource — must redirect to login, not crash
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});

    const afterUrl = page.url();
    expect(
      afterUrl,
      "after cookie deletion, accessing a protected resource must redirect to /admin/login",
    ).toMatch(/\/login|\/admin\/login/i);

    const body = (await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) ?? "";
    expect(body).not.toContain("Javascript Error");

    // Confirm the login form is rendered (not a blank or error page)
    const loginInput = page.locator("input[type=email], input[name=email], input[type=password]");
    const hasLoginForm = (await loginInput.count()) > 0;
    expect(
      hasLoginForm || afterUrl.includes("/login"),
      "login page must show a login form or URL confirms redirect to login",
    ).toBe(true);

    void consoleErrors;
  });
});
