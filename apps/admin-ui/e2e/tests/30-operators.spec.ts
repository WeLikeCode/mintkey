/**
 * 30 — PlatformAdmin: operator promotion.
 *
 * As a platform admin, open Operators, promote a new operator by email into the
 * default tenant, and assert the row appears in the list. Mirrors the platform-
 * admin-gated flow in 29-tenants-pa.spec.ts.
 *
 * admin-api makes no Keycloak call at promotion time — the operator is a "shadow"
 * row whose oidc_sub binds lazily on first OIDC login (ADR-0031 D3). A green
 * promote→list is sufficient proof for the UI slice.
 *
 * Source: operator-management OpenSpec change; ADR-0031; ADR-0019.
 */

import { test, expect } from "../fixtures/test.js";
import { OperatorsPage } from "../pages/operators.js";

test.describe("30 — PlatformAdmin: operator promotion", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS env var is required").not.toEqual("");
  });

  test("Operators list is reachable and shows the operators table", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/operators", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 30_000 });

    const jsErrorCount = await page.locator("text=Javascript Error").count();
    expect(jsErrorCount, "No Javascript Error should appear on the page").toBe(0);

    // At least the bootstrap operator (admin@mintkey.internal) should be listed.
    const rowCount = await page.locator("table tbody tr").count();
    expect(rowCount, `Expected ≥1 operator row, got ${rowCount}`).toBeGreaterThanOrEqual(1);

    void consoleErrors;
  });

  test("PlatformAdmin promotes a new operator by email and the row appears", async ({
    page,
    consoleErrors,
  }) => {
    const operators = new OperatorsPage(page);

    // Resolve a valid home tenant id (t_default) from the Tenants list — the id
    // column is the first cell of each row and carries the tenant_ wire ID.
    await page.goto("/admin/resources/tenants", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 30_000 });
    const tenantId = (await page.locator("table tbody tr td").first().innerText()).trim();
    expect(tenantId, "Expected a tenant id from the tenants list").not.toEqual("");

    const email = `e2e-op-${Date.now()}@corp.example`;

    const response = await operators.promoteOperator({
      email,
      tenantId,
      displayName: "E2E Promoted Operator",
    });

    const body = (await response.json()) as { notice?: { message?: string; type?: string } };
    expect(body.notice?.type, `promote notice was: ${JSON.stringify(body.notice)}`).toBe("success");
    expect(body.notice?.message ?? "").toContain(email);

    // The new operator appears in the list.
    await operators.gotoList();
    await page.waitForLoadState("networkidle", { timeout: 30_000 });
    await expect(operators.getRowByEmail(email)).toHaveCount(1, { timeout: 15_000 });

    void consoleErrors;
  });
});
