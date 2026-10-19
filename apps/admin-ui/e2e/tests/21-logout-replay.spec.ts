/**
 * W5 (issue #345): a logged-out session cookie is refused by admin-api.
 *
 * Log in through the real Keycloak UI, keep a copy of the `mintkey_session`
 * cookie, log out through the UI (the POST form in the AdminJS top bar), then
 * replay the old cookie against `GET /v1/auth/whoami`. admin-api must answer
 * 401: the session row is gone, so the 15 s whoami cache must not keep it alive
 * either.
 *
 * This spec runs in the repository's Playwright workflow, not in the L4 gates
 * (the gate sandbox has no Docker). Every criterion of the logout change is
 * proven by the admin-api pytest and admin-ui Vitest suites.
 *
 * Session-isolation note: test (a) of 21-logout-session.spec.ts explains why a
 * logout must not use the shared storageState. This spec does the same: it
 * clears the context cookies, logs in a fresh session, and logs that one out.
 */

import { test, expect, request as playwrightRequest } from "@playwright/test";
import { ADMIN_API } from "../env.js";

const ADMIN_EMAIL = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
const ADMIN_PASS = process.env.PLAYWRIGHT_PASS ?? "";

test.describe("21 — Logout replay", () => {
  test.beforeAll(() => {
    expect(ADMIN_PASS, "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("replaying the old mintkey_session after logout answers 401", async ({ page }) => {
    if (!ADMIN_PASS) {
      test.skip(true, "PLAYWRIGHT_PASS not set");
      return;
    }

    await page.context().clearCookies();

    await page.goto("/auth/start", { waitUntil: "domcontentloaded" });
    const kcUsername = page.locator("#username");
    const kcPassword = page.locator("#password");
    const kcSubmit = page.locator("#kc-login");

    const hasKeycloakForm =
      (await kcUsername.count()) > 0 && (await kcPassword.count()) > 0;
    if (!hasKeycloakForm) {
      test.skip(true, "Keycloak login form not visible; the stack is not running");
      return;
    }

    await kcUsername.fill(ADMIN_EMAIL);
    await kcPassword.fill(ADMIN_PASS);
    await Promise.all([
      page.waitForURL(
        (url) => url.href.includes("/admin") && !url.href.includes("/auth/"),
        { timeout: 30_000 },
      ),
      kcSubmit.click(),
    ]);

    const sessionCookie = (await page.context().cookies()).find(
      (cookie) => cookie.name === "mintkey_session",
    );
    expect(sessionCookie, "login must set the mintkey_session cookie").toBeDefined();
    const replayedValue = sessionCookie!.value;
    expect(replayedValue).not.toEqual("");

    const logoutButton = page.locator('[data-testid="logout"]').first();
    if ((await logoutButton.count()) > 0) {
      await Promise.all([
        page
          .waitForURL((url) => /\/login/i.test(url.href), { timeout: 15_000 })
          .catch(() => {}),
        logoutButton.click(),
      ]);
    } else {
      await page.goto("/admin/logout", { waitUntil: "domcontentloaded" });
      const confirm = page.locator('[data-testid="logout-confirm"]');
      expect(confirm, "the confirmation page must offer the logout button").toHaveCount(1);
      await Promise.all([
        page
          .waitForURL((url) => /\/login/i.test(url.href), { timeout: 15_000 })
          .catch(() => {}),
        confirm.click(),
      ]);
    }
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});

    const replays = await playwrightRequest.newContext({ ignoreHTTPSErrors: true });
    try {
      const replayed = await replays.get(`${ADMIN_API}/v1/auth/whoami`, {
        headers: { Cookie: `mintkey_session=${replayedValue}` },
      });
      expect(
        replayed.status(),
        "a copied mintkey_session must not be accepted after logout",
      ).toBe(401);

      const body = (await replayed.json().catch(() => ({}))) as Record<string, unknown>;
      expect(body["mintkey:code"]).toBe("unauthenticated");
    } finally {
      await replays.dispose();
    }
  });
});
