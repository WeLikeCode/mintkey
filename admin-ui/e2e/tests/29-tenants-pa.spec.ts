/**
 * W0 migration: PlatformAdmin sees tenants list.
 *
 * Migrated from admin-ui/tests/e2e/tenants-platform-admin.spec.ts.
 * Verifies that the bootstrap operator (PlatformAdmin) can navigate to
 * /admin/resources/tenants and see ≥1 row including t_default.
 *
 * Root cause fixed: X-Platform-Admin header not forwarded; /v1/tenants
 * returned 403 for PlatformAdmin. Source: fix-tenants-403 chunk; ADR-0016.3.
 */

import { test, expect } from "../fixtures/test.js";

test.describe("29 — PlatformAdmin: tenants list", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS env var is required").not.toEqual("");
  });

  test("PlatformAdmin sees tenants list with ≥1 row including t_default", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/tenants", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 30_000 });

    const jsErrorCount = await page.locator("text=Javascript Error").count();
    expect(jsErrorCount, "No Javascript Error should appear on the page").toBe(0);

    const rowCount = await page.locator("table tbody tr").count();
    expect(rowCount, `Expected ≥1 row in tenants table, got ${rowCount}`).toBeGreaterThanOrEqual(1);

    const pageContent = await page.content();
    expect(pageContent, "Expected t_default to appear in the tenants list").toContain("t_default");

    void consoleErrors;
  });
});
