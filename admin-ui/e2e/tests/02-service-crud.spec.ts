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

import { test, expect, type Page, type Response } from "@playwright/test";
import { ServicesPage } from "../pages/services.js";
import {
  createTestService,
  resetCleanupQueue,
} from "../fixtures/test-data.js";

test.describe("Tier 2 — Service CRUD (F-OP-02)", () => {
  let page: Page;
  let svc: ServicesPage;
  const token = process.env.PLAYWRIGHT_API_JWT ?? "";

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

    await page.getByLabel("name").fill(svcName);
    await page.getByLabel("slug").fill(svcSlug);
    await page.getByLabel("base url").fill("https://test.example.com/api");

    const schemeSelect = page.locator("select").filter({ hasText: /auth scheme/i });
    await schemeSelect.selectOption("api_key_header");

    const [response] = await Promise.all([
      page.waitForResponse((r: Response) => r.url().includes("/v1/tenants") && r.request().method() === "POST", { timeout: 10_000 }),
      page.getByRole("button", { name: /save|create/i }).click(),
    ]);

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.id).toBeTruthy();
    expect(body.name).toBe(svcName);

    await expect(page).toHaveURL(/\/admin\/resources\/services$/);
    await expect(svc.getRowByName(svcName)).toBeVisible();
  });

  test("3. view service detail shows all fields", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const id = await createTestService({ tenantId, name: "DetailTest", slug: "detail-test", baseUrl: "https://detail.example.com" }, token);
    await svc.gotoShow(id);
    await expect(page.locator("td, dd").filter({ hasText: "DetailTest" })).toBeVisible();
    await expect(page.locator("td, dd").filter({ hasText: "detail-test" })).toBeVisible();
  });

  test("4. edit service updates fields", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const id = await createTestService({ tenantId, name: "EditTest", slug: "edit-test" }, token);

    await svc.gotoEdit(id);
    const newName = "EditTest-Updated-" + Date.now();
    await page.getByLabel("name").fill(newName);

    await Promise.all([
      page.waitForResponse((r: Response) => r.url().includes(`/services/${id}`) && r.request().method() === "PATCH", { timeout: 10_000 }),
      page.getByRole("button", { name: /save/i }).click(),
    ]);

    await svc.gotoShow(id);
    await expect(page.locator("td, dd").filter({ hasText: newName })).toBeVisible();
  });

  test("5. test connection action fires", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const id = await createTestService({ tenantId, name: "TestConn", slug: "test-conn", baseUrl: "https://localhost:1" }, token);
    const result = await svc.testService(id) as Response;

    expect(result.status()).toBe(200);
    const body = await result.json();
    expect(body).toHaveProperty("ok");
  });

  test("6. delete service removes from list", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const id = await createTestService({ tenantId, name: "DelTest", slug: "del-test" }, token);
    await svc.deleteService(id);

    await svc.gotoList();
    await expect(svc.getRowByName("DelTest")).not.toBeVisible();
  });
});