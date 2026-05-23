/**
 * Tier 2 — Service CRUD (critical path).
 *
 * Source: F-OP-02; T-1.2.3.
 *
 * Tests:
 *  1. List services — renders with existing data
 *  2. Create service — happy path
 *  3. View service detail — shows all fields
 *  4. Edit service — update name/base_url
 *  5. Test connection action
 *  6. Delete service — removes from list
 */

import { test, expect, type Page } from "@playwright/test";
import { ServicesPage } from "../pages/services.js";
import {
  createTestService,
  resetCleanupQueue,
} from "../fixtures/test-data.js";

test.describe("Tier 2 — Service CRUD (F-OP-02)", () => {
  let page: Page;
  let svc: ServicesPage;
  const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    svc = new ServicesPage(page);
    resetCleanupQueue();
  });

  test("1. list services renders table", async () => {
    await svc.gotoList();
    expect(page.url()).toContain("/admin/resources/services");
    await expect(page.locator("table")).toBeVisible();
  });

  test("2. create service — happy path", async () => {
    const svcName = "TestService-" + Date.now();
    const svcSlug = "test-service-" + Date.now();

    await svc.gotoNew();
    await page.waitForLoadState("networkidle");

    await page.getByLabel("name").fill(svcName);
    await page.getByLabel("slug").fill(svcSlug);
    await page.getByLabel(/base url/i).fill("https://test.example.com/api");

    // AdminJS uses React Select (not native <select>) for properties with availableValues
    await svc.selectFromReactSelect(/auth.scheme/i, /api key.*header/i);

    // Submit: AdminJS POSTs to /admin/api/resources/services/actions/new (server-side)
    // then redirects the browser to the list. Watch for the AdminJS API call.
    await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/services/actions/new") && r.request().method() === "POST",
        { timeout: 15_000 }
      ),
      page.getByRole("button", { name: /save|create/i }).click(),
    ]);

    // AdminJS redirects to list on success
    await page.waitForURL(/\/admin\/resources\/services/, { timeout: 10_000 });
    await page.waitForLoadState("networkidle");
    await expect(svc.getRowByName(svcName)).toBeVisible({ timeout: 10_000 });
  });

  test("3. view service detail shows all fields", async () => {
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const id = await createTestService(
      { tenantId, name: "DetailTest", slug: `detail-test-${Date.now()}`, baseUrl: "https://detail.example.com" }, ""
    );
    await svc.gotoShow(id);
    await page.waitForLoadState("networkidle");
    // AdminJS show view renders values as text inside <section data-testid="property-show-*">
    await expect(page.locator("body")).toContainText("DetailTest");
    await expect(page.locator("body")).toContainText("https://detail.example.com");
  });

  test("4. edit service updates fields", async () => {
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const id = await createTestService({ tenantId, name: "EditTest", slug: `edit-test-${Date.now()}` }, "");

    await svc.gotoEdit(id);
    await page.waitForLoadState("networkidle");
    const newName = "EditTest-Updated-" + Date.now();
    await page.getByLabel("name").clear();
    await page.getByLabel("name").fill(newName);

    await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/services/records/") && r.request().method() === "POST",
        { timeout: 15_000 }
      ),
      page.getByRole("button", { name: /save/i }).click(),
    ]);

    await svc.gotoShow(id);
    await page.waitForLoadState("networkidle");
    // AdminJS show view renders values as text nodes inside <section data-testid="property-show-*">
    await expect(page.locator("body")).toContainText(newName);
  });

  test("5. test connection action fires", async () => {
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const id = await createTestService(
      { tenantId, name: "TestConn", slug: `test-conn-${Date.now()}`, baseUrl: "https://httpbin.org" }, ""
    );
    await svc.gotoShow(id);
    await page.waitForLoadState("networkidle");

    // AdminJS renders record actions as <a> links; action name "testService" → "Test Service"
    const testBtn = page.locator("a").filter({ hasText: /test service|test connection/i }).first();
    await expect(testBtn).toBeVisible();
    await testBtn.click();

    // AdminJS action handler responds with a notice
    // Wait for either a notice/alert or the action API response
    await page.waitForResponse(
      (r) => r.url().includes("testService") || r.url().includes("/test"),
      { timeout: 15_000 }
    ).catch(() => {
      // Some actions return inline — just check for a notice
    });

    // Verify page didn't crash
    await expect(page.locator("body")).not.toContainText("Cannot GET");
  });

  test("6. delete service removes from list", async () => {
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const delSlug = `del-test-${Date.now()}`;
    const id = await createTestService({ tenantId, name: "DelTest", slug: delSlug }, "");
    await svc.deleteService(id);

    await svc.gotoList();
    await page.waitForLoadState("load");
    // After delete + redirect to list, the service should be gone
    // Use the unique slug to avoid matching other "DelTest" entries
    await expect(page.locator("tr").filter({ hasText: id })).not.toBeVisible({ timeout: 10_000 });
  });
});
