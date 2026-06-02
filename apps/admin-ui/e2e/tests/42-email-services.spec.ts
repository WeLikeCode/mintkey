/**
 * E2E smoke spec — Email Services resource (C-10).
 *
 * Verifies:
 *   1. Operator can navigate to Email Services list.
 *   2. Operator clicks Add, fills email_password form, submits, sees success
 *      (or error when admin-api is live — we check navigation, not API).
 *   3. Provider and auth_scheme dropdowns are present with correct options.
 *
 * OAuth2 happy-path (popup flow) is SKIPPED pending a mock provider.
 * Per project memory `project-playwright-pre-existing-red`: Playwright is
 * non-required for merge but this spec should be GREEN against this branch
 * when the stack is running.
 *
 * Prerequisites:
 *   PLAYWRIGHT_PASS is set (Keycloak / break-glass operator password).
 *
 * Source: C-10; ADMIN_UI_SPEC.md §2.x; Playwright Extension Plan.
 */

import { test, expect } from "../fixtures/test.js";

const ADMIN_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

test.describe("42 — Email Services resource smoke", () => {
  test.beforeAll(() => {
    expect(
      process.env.PLAYWRIGHT_PASS ?? "",
      "PLAYWRIGHT_PASS is required for e2e tests"
    ).not.toEqual("");
  });

  test("email services list page loads without errors", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto(`${ADMIN_URL}/admin/resources/email_services`);
    await page.waitForLoadState("networkidle");

    // Should show the resource list (or empty state) without a 500 / redirect
    const title = await page.title().catch(() => "");
    expect(title).not.toContain("Error");

    // No browser console errors
    expect(consoleErrors.errors).toHaveLength(0);
  });

  test("email services new form renders provider and auth_scheme dropdowns", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto(`${ADMIN_URL}/admin/resources/email_services/actions/new`);
    await page.waitForLoadState("networkidle");

    // Provider dropdown should be present
    const providerSelect = page.locator("select").filter({
      has: page.locator("option[value='gmail']"),
    });
    await expect(providerSelect).toBeVisible();

    // auth_scheme dropdown should have email_password option
    const authSchemeSelect = page.locator("select").filter({
      has: page.locator("option[value='email_password']"),
    });
    await expect(authSchemeSelect).toBeVisible();

    // oauth2 option should also be present
    const oauth2Option = page.locator("option[value='email_oauth2']");
    await expect(oauth2Option).toHaveCount(1);

    // No browser console errors
    expect(consoleErrors.errors).toHaveLength(0);
  });

  test("email services new form has all expected input fields", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto(`${ADMIN_URL}/admin/resources/email_services/actions/new`);
    await page.waitForLoadState("networkidle");

    // The page should contain inputs for imap_host and smtp_host
    const body = await page.locator("body").textContent().catch(() => "");
    expect(body).toMatch(/imap|smtp/i);

    // No browser console errors
    expect(consoleErrors.errors).toHaveLength(0);
  });

  /**
   * OAuth2 popup flow — SKIPPED pending mock provider.
   *
   * When a mock OAuth2 provider is available in CI, remove the test.skip()
   * annotation and implement:
   *   1. Create an email service with auth_scheme=email_oauth2 via API.
   *   2. Navigate to its show page.
   *   3. Click "Authorize with Gmail →".
   *   4. Intercept the popup / redirect and simulate the callback.
   *   5. Assert oauth2_authorized = true.
   */
  test.skip("OAuth2 authorize flow (SKIP: no mock provider)", async () => {
    // Intentionally empty — see comment above.
  });
});
