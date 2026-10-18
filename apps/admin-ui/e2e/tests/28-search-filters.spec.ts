/**
 * W0 migration: search and contextual filters.
 *
 * Migrated from admin-ui/tests/e2e/search-and-filters.spec.ts.
 * Verifies that filter inputs cause real data narrowing — not just URL param
 * presence.
 *
 * The original baselines (services unfiltered=126 with one demo-crm, agents unfiltered≈480 with
 * 12 "smoke" agents) came from a long-lived dev database. A fresh stack has none of those rows, so
 * beforeAll seeds what the assertions need: a demo-crm service plus a non-matching one, and a smoke
 * agent plus a non-matching one.
 *
 * Source: admin-ui-search-filter-wiring acceptance criteria #3, #4.
 */

import { test, expect } from "../fixtures/test.js";
import { TENANT_ID } from "../env.js";
import { createTestAgent, createTestService } from "../fixtures/test-data.js";

test.describe("28 — Search and filters", () => {
  test.beforeAll(async () => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS env var is required").not.toEqual("");
    expect(TENANT_ID, "PLAYWRIGHT_TENANT_ID is required to seed the search fixtures").not.toEqual("");
    const uniq = Date.now().toString(36);
    // createTestService appends a unique suffix, so these names are "demo-crm-<suffix>" / "billing-<suffix>".
    await createTestService({ tenantId: TENANT_ID, name: "demo-crm", baseUrl: "https://crm.example.com" });
    await createTestService({ tenantId: TENANT_ID, name: "billing-api", baseUrl: "https://billing.example.com" });
    await createTestAgent({ tenantId: TENANT_ID, name: `smoke-agent-${uniq}` });
    await createTestAgent({ tenantId: TENANT_ID, name: `reporting-agent-${uniq}` });
  });

  async function countTableRows(page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never): Promise<number> {
    return page.locator("table tbody tr").count();
  }

  async function waitForList(page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never): Promise<void> {
    await page.locator('table, :text("No records")').first().waitFor({ state: "visible", timeout: 25_000 });
  }

  test("Services: q=crm narrows to ≤5 rows containing demo-crm", async ({ page, consoleErrors }) => {
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await waitForList(page);
    const baselineCount = await countTableRows(page);

    await page.goto("/admin/resources/services?filters.q=crm", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    expect(page.url()).toContain("filters.q=crm");
    const filteredCount = await countTableRows(page);
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";

    expect(filteredCount, "q=crm should return strictly fewer rows than baseline").toBeLessThan(baselineCount);
    expect(filteredCount, "q=crm should return ≥1 row (demo-crm exists)").toBeGreaterThanOrEqual(1);
    expect(filteredCount, "q=crm should return ≤5 rows").toBeLessThanOrEqual(5);
    expect(body, "demo-crm must appear in filtered table").toContain("demo-crm");
    expect(body).not.toContain("Javascript Error");
    expect(body).not.toContain("Application error");
    void consoleErrors;
  });

  test("Services: q=% returns 0 rows (LIKE wildcard escaped)", async ({ page, consoleErrors }) => {
    await page.goto("/admin/resources/services?filters.q=%25", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    expect(page.url()).toMatch(/filters\.q=%25|filters\.q=%/);
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    const filteredCount = await countTableRows(page);

    expect(filteredCount, "q=% should return 0 rows (LIKE-escaped)").toBe(0);
    expect(body).not.toContain("Javascript Error");
    expect(body).not.toContain("Application error");
    void consoleErrors;
  });

  test("Tenants: q=t_default filter is forwarded and page renders without error", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/tenants", { waitUntil: "domcontentloaded" });
    await waitForList(page);
    const baselineCount = await countTableRows(page);

    await page.goto("/admin/resources/tenants?filters.q=t_default", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    expect(page.url()).toContain("filters.q=t_default");
    const filteredCount = await countTableRows(page);
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";

    expect(body).not.toContain("Javascript Error");
    expect(body).not.toContain("Application error");
    if (baselineCount > 0) {
      expect(
        filteredCount,
        "q=t_default should return ≤ baseline rows when PlatformAdmin view active",
      ).toBeLessThanOrEqual(baselineCount);
      expect(body, "t_default must appear in the filtered table").toContain("t_default");
    }
    void consoleErrors;
  });

  test("Agents: q=smoke narrows list strictly below baseline", async ({ page, consoleErrors, browserName }) => {
    // webkit: AdminJS URL filter params not processed — returns 0 rows.
    // Tracked: PLAYWRIGHT_EXTENSION_PLAN.md W8.
    test.skip(browserName === "webkit", "AdminJS URL filter params not processed on webkit");
    await page.goto("/admin/resources/agents", { waitUntil: "domcontentloaded" });
    await waitForList(page);
    const baselineCount = await countTableRows(page);

    await page.goto("/admin/resources/agents?filters.q=smoke", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    expect(page.url()).toContain("filters.q=smoke");
    const filteredCount = await countTableRows(page);
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";

    expect(filteredCount, "q=smoke should return strictly fewer rows than baseline").toBeLessThan(baselineCount);
    expect(filteredCount, "q=smoke should return ≥1 row").toBeGreaterThanOrEqual(1);
    expect(body).not.toContain("Javascript Error");
    expect(body).not.toContain("Application error");
    void consoleErrors;
  });

  test("Audit Events: event_type filter applied without error (0 results OK)", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto(
      "/admin/resources/audit_events?filters.event_type=service.registered",
      { waitUntil: "domcontentloaded" },
    );
    await waitForList(page);

    expect(page.url()).toContain("filters.event_type=service.registered");
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";

    expect(body).not.toContain("Javascript Error");
    expect(body).not.toContain("Application error");
    const hasTable = (await page.locator("table").count()) > 0;
    const hasNoRecords = /No records/i.test(body);
    expect(hasTable || hasNoRecords, "Should show table or No records after event_type filter").toBe(true);
    void consoleErrors;
  });
});
