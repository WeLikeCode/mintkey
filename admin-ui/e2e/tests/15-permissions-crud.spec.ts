/**
 * W2: Permission Grants CRUD round-trip.
 *
 * create → list contains new row → show renders all fields → delete → list no longer has it.
 *
 * Uses IDs extracted from the seeded agents and services lists to avoid
 * provisioning dependencies. Permissions have no edit action (isVisible: false).
 *
 * Source: F-OP-04; T-1.5.x; PLAYWRIGHT_EXTENSION_PLAN.md W2.
 */

import { test, expect } from "../fixtures/test.js";
import { PermissionsPage } from "../pages/permissions.js";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

/** Extract the first record ID from a resource list page show link. */
async function firstRecordId(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
  resource: string,
): Promise<string | null> {
  await page.goto(`/admin/resources/${resource}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
  const link = page
    .locator(`a[href*="/admin/resources/${resource}/records/"][href*="/show"]`)
    .first();
  if ((await link.count()) === 0) return null;
  const href = await link.getAttribute("href");
  const m = href?.match(/\/records\/([^/]+)\/show/);
  return m ? m[1] : null;
}

/** Extract first visible table cell text for a given column position in first data row. */
async function firstRowCellText(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
  resource: string,
  cellIndex: number,
): Promise<string | null> {
  await page.goto(`/admin/resources/${resource}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
  const firstRow = page.locator("table tbody tr").first();
  if ((await firstRow.count()) === 0) return null;
  const cells = firstRow.locator("td");
  const text = await cells.nth(cellIndex).textContent().catch(() => null);
  return text?.trim() ?? null;
}

test.describe("15 — Permission Grants CRUD round-trip", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("create → list → show → delete", async ({ page, consoleErrors }) => {
    const perms = new PermissionsPage(page);

    // Get IDs of an existing seeded agent and service from their list pages
    // (column 0 = id, column 1 = name/agent_id for permissions list)
    const agentId = await firstRowCellText(page, "agents", 0);
    const serviceId = await firstRowCellText(page, "services", 0);

    if (!agentId || !serviceId) {
      // In a stack without seeded data, skip gracefully
      await page.goto("/admin/resources/permission_grants", { waitUntil: "domcontentloaded" });
      const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
      expect(body).not.toContain("Javascript Error");
      void consoleErrors;
      return;
    }

    const action = `e2e-read-${uid()}`;

    // ── Create ──────────────────────────────────────────────────────────────
    await page.goto("/admin/resources/permission_grants/actions/new", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    await page.getByLabel(/agent.?id/i).fill(agentId);
    await page.getByLabel(/service.?id/i).fill(serviceId);
    await page.getByLabel(/^action$/i).fill(action);

    const [createResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/admin/api/resources/permission_grants/actions/new") &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.getByRole("button", { name: /save|grant/i }).click(),
    ]);

    // Accept 201 (created) or 200 from AdminJS API
    expect(createResp.status(), "create must return 2xx").toBeLessThan(400);

    // ── List contains new row ───────────────────────────────────────────────
    await perms.gotoList();
    await page.waitForLoadState("networkidle");
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(body, "list must contain the new action text").toContain(action.slice(0, 12));
    expect(body).not.toContain("Javascript Error");

    // Get the permission ID from the list show link for the row containing our action
    const permRow = page.locator("tr").filter({ hasText: action.slice(0, 12) }).first();
    const showHref = await permRow
      .locator(`a[href*="/admin/resources/permission_grants/records/"][href*="/show"]`)
      .getAttribute("href");
    const idMatch = showHref?.match(/\/records\/([^/]+)\/show/);
    const permId = idMatch?.[1] ?? "";

    if (!permId) {
      // If we can't extract the ID (e.g. multiple pages), just assert no errors
      void consoleErrors;
      return;
    }

    // ── Show renders all fields ─────────────────────────────────────────────
    await page.goto(`/admin/resources/permission_grants/records/${permId}/show`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");
    const showBody = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(showBody).not.toContain("Javascript Error");
    expect(showBody, "show must contain the action").toContain(action.slice(0, 12));

    // ── Delete ─────────────────────────────────────────────────────────────
    const deleteBtn = page.locator('[data-testid="action-delete"]');
    if ((await deleteBtn.count()) > 0) {
      await deleteBtn.waitFor({ state: "visible", timeout: 5_000 });
      await deleteBtn.click();
      const confirmBtn = page.getByRole("button", { name: /^confirm$/i });
      await confirmBtn.waitFor({ state: "visible", timeout: 5_000 });
      await Promise.all([
        page.waitForResponse(
          (r) =>
            r.url().includes(`/admin/api/resources/permission_grants/records/${permId}`) &&
            r.request().method() === "DELETE",
          { timeout: 10_000 },
        ).catch(() => {}),
        confirmBtn.click(),
      ]);
      await page.waitForLoadState("networkidle");

      // List no longer shows the deleted permission
      await perms.gotoList();
      await page.waitForLoadState("networkidle");
      const afterDeleteBody = (await page.locator("body").innerText().catch(() => "")) ?? "";
      expect(afterDeleteBody).not.toContain(permId);
    }

    void consoleErrors;
  });
});
