/**
 * W1: Services CRUD round-trip.
 *
 * create → list contains new row → show renders all fields →
 * edit one field → show reflects edit → delete → list no longer contains it.
 *
 * Source: F-OP-02; T-1.2.3; PLAYWRIGHT_EXTENSION_PLAN.md W1.
 */

import { test, expect } from "../fixtures/test.js";
import { ServicesPage } from "../pages/services.js";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

test.describe("12 — Services CRUD round-trip", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // webkit: AdminJS/Axios throws access control errors for localhost API calls
  // in WebKit's stricter CORS enforcement. Tracked: PLAYWRIGHT_EXTENSION_PLAN.md W8.
  test.skip(({ browserName }) => browserName === "webkit",
    "AdminJS/Axios access control errors on webkit — localhost CORS differs");

  test("create → list → show → edit → delete", async ({ page, consoleErrors }) => {
    const svc = new ServicesPage(page);
    const name = `e2e-svc-${uid()}`;
    const baseUrl = "https://test.example.com/api";
    const updatedUrl = "https://updated.example.com/api";

    // ── Create ──────────────────────────────────────────────────────────────
    // The AdminJS default "new" form was replaced by ServiceCreateForm (0b04288, UX-C6 Phase 3):
    // data-testid fields, native auth-scheme <select>, no slug input, in-page success banner.
    // (The UX-C5 "land on the show page" intent is kept: the banner's "View service" link goes there.)
    await svc.gotoNew();
    await page.locator("[data-testid='service-create-form']").waitFor({ state: "visible", timeout: 15_000 });
    await page.locator("[data-testid='field-input-name']").fill(name);
    await page.locator("[data-testid='field-input-base_url']").fill(baseUrl);
    await page.locator("[data-testid='field-select-auth_scheme']").selectOption("api_key_header");

    const [createResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/admin/api/resources/services/actions/new") &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator("[data-testid='service-create-submit']").click(),
    ]);
    expect(createResp.status(), "create must return 2xx").toBeLessThan(400);

    await page.locator("[data-testid='service-create-success']").waitFor({ state: "visible", timeout: 15_000 });
    await page.locator("[data-testid='skip-to-service-btn']").click();
    await page.waitForURL(
      /\/admin\/resources\/services\/records\/[^/]+\/show/,
      { timeout: 10_000 },
    );
    await page.waitForLoadState("networkidle");

    // Confirm the show page actually rendered the service
    const showUrlAfterCreate = page.url();
    expect(showUrlAfterCreate, "redirect URL must be the show page").toMatch(
      /\/admin\/resources\/services\/records\/[^/]+\/show/,
    );
    const showBodyAfterCreate = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(showBodyAfterCreate, "show page after create must contain the service name").toContain(name);

    // ── List contains new row ───────────────────────────────────────────────
    await svc.gotoList();
    await page.waitForLoadState("networkidle");
    const row = svc.getRowByName(name);
    await expect(row, "list must show new service row").toBeVisible({ timeout: 10_000 });

    // Extract the service ID from the show link in the row
    const showHref = await row.locator(`a[href*="/admin/resources/services/records/"][href*="/show"]`).getAttribute("href");
    const idMatch = showHref?.match(/\/records\/([^/]+)\/show/);
    const serviceId = idMatch?.[1] ?? "";
    expect(serviceId, "could not extract service ID from list row").not.toEqual("");

    // ── Show renders all fields ─────────────────────────────────────────────
    await svc.gotoShow(serviceId);
    await page.waitForLoadState("networkidle");
    const showBody = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(showBody, "show page must contain the service name").toContain(name);
    expect(showBody, "show page must contain the base URL").toContain(baseUrl);

    // ── Edit one field ─────────────────────────────────────────────────────
    await svc.gotoEdit(serviceId);
    await page.waitForLoadState("networkidle");
    await page.getByLabel(/base url/i).fill(updatedUrl);

    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/services/records/${serviceId}`) &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.getByRole("button", { name: /save/i }).click(),
    ]);

    // Show reflects edit
    await svc.gotoShow(serviceId);
    await page.waitForLoadState("networkidle");
    const editedBody = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(editedBody, "show page must reflect updated base URL").toContain(updatedUrl);

    // ── Delete ─────────────────────────────────────────────────────────────
    await svc.deleteService(serviceId);
    await page.waitForURL(/\/admin\/resources\/services/, { timeout: 10_000 });
    await page.waitForLoadState("networkidle");

    // List no longer contains the row
    await svc.gotoList();
    await page.waitForLoadState("networkidle");
    const rowAfterDelete = page.locator("tr").filter({ hasText: name });
    await expect(rowAfterDelete, "list must not contain deleted service").not.toBeVisible({
      timeout: 5_000,
    });

    void consoleErrors;
  });
});
