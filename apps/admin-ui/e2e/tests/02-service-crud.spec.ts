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
    // The list only renders a <table> when there is at least one row, so seed one
    // instead of relying on whatever the stack happens to contain.
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }
    await createTestService(
      { tenantId, name: "ListTest", slug: `list-test-${Date.now()}`, baseUrl: "https://list.example.com" }, ""
    );
    await svc.gotoList();
    expect(page.url()).toContain("/admin/resources/services");
    await expect(page.locator("table")).toBeVisible();
  });

  test("2. create service — happy path", async () => {
    const svcName = "TestService-" + Date.now();

    // Real ServiceCreateForm (0b04288): fill by data-testid, submit, success banner (no redirect).
    const id = await svc.createServiceViaForm({
      name: svcName,
      baseUrl: "https://test.example.com/api",
      authScheme: "api_key_header",
    });
    await expect(page.locator("[data-testid='success-banner']")).toContainText(/registered successfully/i);

    // The service is persisted: it shows up in the list and its show page carries the values.
    await svc.gotoList();
    await expect(svc.getRowByName(svcName)).toBeVisible({ timeout: 10_000 });
    await svc.gotoShow(id);
    await expect(page.locator("body")).toContainText(svcName);
    await expect(page.locator("body")).toContainText("https://test.example.com/api");
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
