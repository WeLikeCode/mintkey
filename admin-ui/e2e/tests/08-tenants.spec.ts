/**
 * Tier 3 — Multi-tenant operations (PlatformAdmin only).
 *
 * Source: T-1.12.4; ADR-0016.3; Req 13.
 */

import { test, expect, type Page } from "@playwright/test";
import { TenantsPage } from "../pages/tenants.js";
import { createTestTenant, resetCleanupQueue } from "../fixtures/test-data.js";

test.describe("Tier 3 — Tenants (PlatformAdmin)", () => {
  let page: Page;
  let tenants: TenantsPage;

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    tenants = new TenantsPage(page);
    resetCleanupQueue();
  });

  test("1. tenants resource is visible in navigation", async () => {
    await tenants.gotoList();
    await page.waitForLoadState("networkidle");
    const isPlatformAdmin = process.env.PLAYWRIGHT_IS_PLATFORM_ADMIN === "true";
    if (isPlatformAdmin) {
      // AdminJS renders sidebar as a Box div with data-css="sidebar", not a <nav> element
      await expect(page.locator('[data-css="sidebar"]')).toContainText("Tenants", { timeout: 10_000 });
    }
  });

  test("2. PlatformAdmin can create tenant", async () => {
    const isPlatformAdmin = process.env.PLAYWRIGHT_IS_PLATFORM_ADMIN === "true";
    if (!isPlatformAdmin) {
      test.skip(true, "Requires PlatformAdmin role");
      return;
    }

    const tenantName = "E2ETenant-" + Date.now();
    await tenants.createTenant({ slug: tenantName.toLowerCase(), display_name: tenantName });

    // After successful creation AdminJS redirects to the tenants list
    await expect(page).toHaveURL(/\/admin\/resources\/tenants/, { timeout: 10_000 });
  });

  test("3. PlatformAdmin can use all_tenants toggle", async () => {
    const isPlatformAdmin = process.env.PLAYWRIGHT_IS_PLATFORM_ADMIN === "true";
    if (!isPlatformAdmin) {
      test.skip(true, "Requires PlatformAdmin role");
      return;
    }

    await tenants.enablePlatformAdminView();
    expect(page.url()).toContain("/admin/resources/tenants");
  });

  test("4. cross-tenant isolation — operator sees only own data", async () => {
    // Placeholder — requires non-PlatformAdmin credentials
  });
});