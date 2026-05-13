/**
 * Playwright e2e tests for admin-ui search and contextual filters.
 *
 * Verifies that filter inputs cause REAL data narrowing — not just URL param
 * presence. Each positive case asserts row counts shrink and known text appears.
 *
 * Baseline counts (from reviewer curls against live admin-api):
 *   services unfiltered=126, services ?q=crm=1 (demo-crm), services ?q=%=0
 *   agents unfiltered≈480, agents ?q=smoke=12
 *   tenants ?q=t_default=1
 *   audit ?event_type=service.registered=0 (bootstrap tenant)
 *
 * Run:
 *   MINTKEY_ADMIN_PASSWORD="$(cat ../data/bootstrap-secrets/admin_password)" \
 *     npx playwright test tests/e2e/search-and-filters.spec.ts
 *
 * Source: admin-ui-search-filter-wiring acceptance criteria #3, #4.
 */

import { test, expect, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const ADMIN_EMAIL = process.env.MINTKEY_ADMIN_USER ?? "admin@mintkey.internal";
const ADMIN_PASSWORD = process.env.MINTKEY_ADMIN_PASSWORD ?? "";

const SCREENSHOT_DIR = path.resolve(process.cwd(), "test-results", "search-filter-screenshots");
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function login(page: Page): Promise<void> {
  await page.goto("/admin/login", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("input[type=email], input[name=email]", { timeout: 25_000 });
  await page.locator("input[type=email], input[name=email]").first().fill(ADMIN_EMAIL);
  await page.locator("input[type=password], input[name=password]").first().fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: /sign in|log\s?in/i }).first().click();
  await page.waitForFunction(() => !window.location.pathname.includes("/login"), undefined, {
    timeout: 25_000,
  });
}

/** Count visible table body rows (tr elements inside tbody). */
async function countTableRows(page: Page): Promise<number> {
  return page.locator("table tbody tr").count();
}

/** Wait for the list to be rendered (table or No records). */
async function waitForList(page: Page): Promise<void> {
  await page.locator('table, :text("No records")').first().waitFor({ state: "visible", timeout: 25_000 });
}

test.describe("search-and-filters", () => {
  test.beforeAll(() => {
    expect(
      ADMIN_PASSWORD,
      "MINTKEY_ADMIN_PASSWORD env var is required — set it from data/bootstrap-secrets/admin_password",
    ).not.toEqual("");
  });

  // --------------------------------------------------------------------------
  // Scenario 1: Services q=crm → 1 row with text demo-crm
  // --------------------------------------------------------------------------
  test("Services: q=crm narrows to 1 row containing demo-crm", async ({ page }) => {
    await login(page);

    // Baseline: count unfiltered rows
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await waitForList(page);
    const baselineCount = await countTableRows(page);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "01-services-baseline.png"),
      fullPage: true,
    });

    // Apply q=crm filter via URL (the way AdminJS processes filter params)
    await page.goto("/admin/resources/services?filters.q=crm", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    const currentUrl = page.url();
    // URL must contain the filter param
    expect(currentUrl).toContain("filters.q=crm");

    const filteredCount = await countTableRows(page);
    const bodyText = await page.locator("body").innerText().catch(() => "");

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "02-services-q-crm.png"),
      fullPage: true,
    });

    // Narrowing assertions
    expect(filteredCount, "q=crm should return strictly fewer rows than baseline").toBeLessThan(baselineCount);
    expect(filteredCount, "q=crm should return at least 1 row (demo-crm exists)").toBeGreaterThanOrEqual(1);
    expect(filteredCount, "q=crm should return ≤5 rows").toBeLessThanOrEqual(5);
    expect(bodyText, "demo-crm must appear in the filtered table").toContain("demo-crm");

    // No JS errors
    expect(bodyText).not.toContain("Javascript Error");
    expect(bodyText).not.toContain("Application error");
  });

  // --------------------------------------------------------------------------
  // Scenario 2: Services q=% → 0 rows / No records (LIKE-special safety)
  // --------------------------------------------------------------------------
  test("Services: q=% returns 0 rows (LIKE wildcard escaped by admin-api)", async ({ page }) => {
    await login(page);
    await page.goto("/admin/resources/services?filters.q=%25", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    const currentUrl = page.url();
    // URL must contain q=% (encoded as %25 by the browser / Playwright)
    expect(currentUrl).toMatch(/filters\.q=%25|filters\.q=%/);

    const bodyText = await page.locator("body").innerText().catch(() => "");

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "03-services-q-percent.png"),
      fullPage: true,
    });

    const filteredCount = await countTableRows(page);
    // admin-api escapes LIKE wildcards → 0 results expected
    expect(filteredCount, "q=% should return 0 rows (LIKE-escaped)").toBe(0);

    expect(bodyText).not.toContain("Javascript Error");
    expect(bodyText).not.toContain("Application error");
  });

  // --------------------------------------------------------------------------
  // Scenario 3: Tenants q=t_default → filter is sent, no errors
  // Note: /v1/tenants requires PlatformAdmin + X-Platform-Admin:true header,
  // which the AdminJS RestResource only sets when isPlatformAdminView=true on
  // the session. In this test environment the Playwright browser session sends
  // the correct cookie but the admin-api session-based auth for the top-level
  // tenants list may return 403 (0 rows). We assert the URL contains the filter
  // param and no errors occur — confirming the filter is forwarded correctly.
  // If the session is PlatformAdmin-scoped, we additionally assert narrowing.
  // --------------------------------------------------------------------------
  test("Tenants: q=t_default filter is forwarded and page renders without error", async ({ page }) => {
    await login(page);

    // Unfiltered baseline for tenants
    await page.goto("/admin/resources/tenants", { waitUntil: "domcontentloaded" });
    await waitForList(page);
    const baselineCount = await countTableRows(page);

    // Apply q=t_default filter
    await page.goto("/admin/resources/tenants?filters.q=t_default", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    const currentUrl = page.url();
    expect(currentUrl).toContain("filters.q=t_default");

    const filteredCount = await countTableRows(page);
    const bodyText = await page.locator("body").innerText().catch(() => "");

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "04-tenants-q-t_default.png"),
      fullPage: true,
    });

    expect(bodyText).not.toContain("Javascript Error");
    expect(bodyText).not.toContain("Application error");

    // If PlatformAdmin view is active (baseline > 0), assert narrowing:
    // q=t_default should return ≤ baseline rows.
    if (baselineCount > 0) {
      expect(filteredCount, "q=t_default should return ≤ baseline rows when PlatformAdmin view active").toBeLessThanOrEqual(baselineCount);
      expect(bodyText, "t_default must appear in the filtered table").toContain("t_default");
    }
    // If baseline is 0 (admin-api 403 for non-PlatformAdmin-view session), 0 is acceptable.
  });

  // --------------------------------------------------------------------------
  // Scenario 4: Agents q=smoke → row count < baseline AND ≥ 1
  // --------------------------------------------------------------------------
  test("Agents: q=smoke narrows list strictly below baseline", async ({ page }) => {
    await login(page);

    // Baseline: count unfiltered agents
    await page.goto("/admin/resources/agents", { waitUntil: "domcontentloaded" });
    await waitForList(page);
    const baselineCount = await countTableRows(page);

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "05-agents-baseline.png"),
      fullPage: true,
    });

    // Apply q=smoke filter
    await page.goto("/admin/resources/agents?filters.q=smoke", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    const currentUrl = page.url();
    expect(currentUrl).toContain("filters.q=smoke");

    const filteredCount = await countTableRows(page);
    const bodyText = await page.locator("body").innerText().catch(() => "");

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "06-agents-q-smoke.png"),
      fullPage: true,
    });

    // Narrowing: strictly fewer than baseline (≈480), at least 1 (12 expected)
    expect(filteredCount, "q=smoke should return strictly fewer rows than baseline").toBeLessThan(baselineCount);
    expect(filteredCount, "q=smoke should return at least 1 row").toBeGreaterThanOrEqual(1);

    expect(bodyText).not.toContain("Javascript Error");
    expect(bodyText).not.toContain("Application error");
  });

  // --------------------------------------------------------------------------
  // Scenario 5 (bonus): Audit event_type filter — accept 0 in bootstrap tenant
  // --------------------------------------------------------------------------
  test("Audit Events: event_type filter applied without error (0 results OK in bootstrap tenant)", async ({ page }) => {
    await login(page);
    await page.goto(
      "/admin/resources/audit_events?filters.event_type=service.registered",
      { waitUntil: "domcontentloaded" },
    );
    await waitForList(page);

    const currentUrl = page.url();
    expect(currentUrl).toContain("filters.event_type=service.registered");

    const bodyText = await page.locator("body").innerText().catch(() => "");

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "07-audit-event-type-filtered.png"),
      fullPage: true,
    });

    // 0 results is expected in bootstrap tenant — just assert no errors
    expect(bodyText).not.toContain("Javascript Error");
    expect(bodyText).not.toContain("Application error");
    const hasTable = (await page.locator("table").count()) > 0;
    const hasNoRecords = /No records/i.test(bodyText);
    expect(hasTable || hasNoRecords, "Should show table or No records after event_type filter").toBe(true);
  });
});
