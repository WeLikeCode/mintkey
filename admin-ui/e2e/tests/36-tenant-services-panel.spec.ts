/**
 * 36 — Tenant show page: services panel (UX-E).
 *
 * Verifies that the TenantServicesPanel component renders on the tenant show
 * page and correctly lists the tenant's services.
 *
 * Assertions:
 *   1. Navigate to the t_default tenant show page.
 *   2. The services panel wrapper element is present.
 *   3. Either:
 *      a. A table with at least one service row is rendered (seeded services
 *         exist), AND clicking the first row's ID link navigates to that
 *         service's show page.
 *      b. The empty state element is rendered when no services are seeded.
 *   4. No React JS error is shown on the page.
 *
 * Notes:
 *   - Does NOT use page.route — hits the real admin-ui at localhost:8081.
 *   - The panel is scoped to the session tenant. When running as the default
 *     operator (t_default tenant), the viewed tenant matches the session, so
 *     no cross-tenant mismatch warning is expected.
 *   - Browser minimum: chromium (webkit excluded — tracked W8 CORS issue).
 *
 * Source: UX-E spec; TenantServicesPanel.tsx; tenants.ts _services_panel property.
 */

import { test, expect } from "../fixtures/test.js";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Bootstrap tenant — known from seed data (same ID used in 30-show-pages.spec.ts).
const TENANT_ID = process.env.MINTKEY_TENANT_ID ?? "9593e3ba-4102-4235-9748-28d35b473214";

const JS_ERROR_NEEDLES = [
  "Javascript Error",
  "JavaScript Error",
  "Minified React error",
  "Objects are not valid as a React child",
  "TypeError",
  "Application error",
];

test.describe("36 — Tenant show page: services panel", () => {
  // webkit: AdminJS/Axios CORS — tracked W8.
  test.skip(({ browserName }) => browserName === "webkit", "webkit CORS — tracked W8");

  test.beforeAll(() => {
    expect(
      process.env.PLAYWRIGHT_PASS ?? "",
      "PLAYWRIGHT_PASS env var is required",
    ).not.toEqual("");
  });

  test("tenant show page renders the services panel without JS errors", async ({
    page,
    consoleErrors,
  }) => {
    // ── 1. Navigate to the tenant show page ───────────────────────────────────
    await page.goto(`/admin/resources/tenants/records/${TENANT_ID}/show`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

    // ── 2. Assert no JS errors ────────────────────────────────────────────────
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    for (const needle of JS_ERROR_NEEDLES) {
      expect(body, `"${needle}" found on tenant show page`).not.toContain(needle);
    }

    // ── 3. Services panel wrapper is present ──────────────────────────────────
    const panel = page.locator('[data-testid="tenant-services-panel"]');
    await panel.waitFor({ state: "visible", timeout: 15_000 });

    // ── 4. Panel is not still in loading state after networkidle ─────────────
    const loadingEl = page.locator('[data-testid="tenant-services-panel-loading"]');
    // Either loading has finished (element gone) or it was never shown
    const isStillLoading = await loadingEl.isVisible().catch(() => false);
    expect(isStillLoading, "Panel should not still be in loading state after networkidle").toBe(false);

    // ── 5. Either table rows or empty state are rendered ──────────────────────
    const tableEl = page.locator('[data-testid="tenant-services-panel-table"]');
    const emptyEl = page.locator('[data-testid="tenant-services-panel-empty"]');
    const errorEl = page.locator('[data-testid="tenant-services-panel-error"]');

    const tableVisible = await tableEl.isVisible().catch(() => false);
    const emptyVisible = await emptyEl.isVisible().catch(() => false);
    const errorVisible = await errorEl.isVisible().catch(() => false);

    expect(
      tableVisible || emptyVisible,
      `Expected either service table or empty state — error visible: ${errorVisible}`,
    ).toBe(true);

    // ── 6. If table is rendered, assert rows and click a row link ─────────────
    if (tableVisible) {
      const rows = page.locator('[data-testid^="tenant-services-panel-row-"]');
      const rowCount = await rows.count();
      expect(rowCount, "Expected at least one service row in the panel").toBeGreaterThanOrEqual(1);

      // Each row should have an ID link pointing to /admin/resources/services/records/<id>/show
      const firstLink = page.locator('[data-testid^="tenant-services-panel-link-"]').first();
      await expect(firstLink).toBeVisible();

      const href = await firstLink.getAttribute("href");
      expect(href, "Service row link must point to the service show page").toMatch(
        /\/admin\/resources\/services\/records\/.+\/show/,
      );

      // Click the link and confirm navigation to the service show page
      await firstLink.click();
      await page.waitForLoadState("domcontentloaded", { timeout: 15_000 });
      expect(page.url(), "After clicking a service row, should be on the service show page").toMatch(
        /\/admin\/resources\/services\/records\/.+\/show/,
      );

      // No JS errors on the service show page either
      const serviceBody = (await page.locator("body").innerText().catch(() => "")) ?? "";
      for (const needle of JS_ERROR_NEEDLES) {
        expect(serviceBody, `"${needle}" on service show page after click`).not.toContain(needle);
      }
    }

    // ── 7. If empty state rendered, assert CTA link is present ───────────────
    if (emptyVisible) {
      const registerLink = page.locator('[data-testid="tenant-services-panel-register-link"]');
      await expect(registerLink).toBeVisible();
      const registerHref = await registerLink.getAttribute("href");
      expect(registerHref).toBe("/admin/resources/services/actions/new");
    }

    void consoleErrors;
  });

  test("screenshot: tenant show page with services panel", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto(`/admin/resources/tenants/records/${TENANT_ID}/show`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

    // Wait for panel to be done loading
    const panel = page.locator('[data-testid="tenant-services-panel"]');
    await panel.waitFor({ state: "visible", timeout: 15_000 });

    // Capture screenshot to test-results dir
    await page.screenshot({
      path: path.resolve(__dirname, "../test-results/tenant-services-panel.png"),
      fullPage: true,
    });

    void consoleErrors;
  });
});
