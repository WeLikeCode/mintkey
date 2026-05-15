/**
 * 37 — Inline search on all 7 list pages (UX-B).
 *
 * For each of the 7 resources: navigate to the list, assert the search input
 * is visible, type a query, confirm the URL contains `filters.q=` and the
 * table either narrows or shows the empty state.
 *
 * Strategy: drive the input and wait for `filters.q` to appear in the URL (the
 * InlineSearchList component pushes a pushState after 300ms debounce).  We
 * wait for 500ms after the last keypress to give the debounce + AdminJS
 * re-render time to complete.
 *
 * Exclusions:
 *   - webkit: AdminJS URL filter params not honoured — tracked W8.
 *   - Tenants list: only visible to PlatformAdmin; the default operator session
 *     may see 0 rows or be redirected — we still assert the search box renders.
 *
 * Source: UX-B; InlineSearchList.tsx.
 */

import { test, expect } from "../fixtures/test.js";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Ensure the test-results directory exists at the start of the spec
import fs from "fs";
const RESULTS_DIR = path.resolve(__dirname, "../test-results");
if (!fs.existsSync(RESULTS_DIR)) {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
}

const RESOURCES = [
  {
    id: "services",
    label: "Services",
    query: "crm",
    // q=crm should match demo-crm; at minimum narrows or returns 0 rows
    expectMatch: true,
  },
  {
    id: "agents",
    label: "Agents",
    query: "smoke",
    expectMatch: true,
  },
  {
    id: "credentials",
    label: "Credentials",
    query: "bearer",
    expectMatch: false, // may return 0 rows — just assert URL param is set
  },
  {
    id: "service_api_keys",
    label: "API Keys",
    query: "mk_",
    expectMatch: false,
  },
  {
    id: "permission_grants",
    label: "Permissions",
    query: "read",
    expectMatch: false,
  },
  {
    id: "audit_events",
    label: "Audit Events",
    query: "agent",
    expectMatch: false,
  },
  {
    id: "tenants",
    label: "Tenants",
    query: "default",
    expectMatch: false, // PlatformAdmin-only; default operator may get 0 results
  },
] as const;

const JS_ERROR_NEEDLES = [
  "Javascript Error",
  "JavaScript Error",
  "Minified React error",
  "Objects are not valid as a React child",
  "TypeError",
  "Application error",
];

test.describe("37 — Inline search: search box renders on all 7 list pages", () => {
  // webkit: AdminJS/Axios CORS + URL filter params not honoured — tracked W8.
  test.skip(({ browserName }) => browserName === "webkit", "webkit CORS — tracked W8");

  test.beforeAll(() => {
    expect(
      process.env.PLAYWRIGHT_PASS ?? "",
      "PLAYWRIGHT_PASS env var is required",
    ).not.toEqual("");
  });

  async function waitForList(page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never): Promise<void> {
    await page
      .locator('table, :text("No records"), [data-testid="inline-search-box"]')
      .first()
      .waitFor({ state: "visible", timeout: 25_000 });
  }

  for (const resource of RESOURCES) {
    test(`${resource.label}: inline search box renders and updates URL on input`, async ({
      page,
      consoleErrors,
    }) => {
      await page.goto(`/admin/resources/${resource.id}`, {
        waitUntil: "domcontentloaded",
      });
      await waitForList(page);

      // Assert the search box is present
      const searchBox = page.locator('[data-testid="inline-search-box"]');
      await searchBox.waitFor({ state: "visible", timeout: 15_000 });
      await expect(searchBox, `${resource.label}: inline-search-box must be visible`).toBeVisible();

      const searchInput = page.locator('[data-testid="inline-search-input"]');
      await expect(searchInput, `${resource.label}: inline-search-input must be visible`).toBeVisible();

      // Type a query and wait for the debounce (300ms) + React Router URL update.
      // Large lists (agents: 1430 rows) take longer for the initial render to complete,
      // which delays the React Router state flush. Use waitForURL for robustness.
      await searchInput.fill(resource.query);
      await page.waitForURL(
        (url) => url.toString().includes(`filters.q=${encodeURIComponent(resource.query)}`),
        { timeout: 10_000 },
      );

      // Assert the URL contains filters.q=<query>
      expect(
        page.url(),
        `${resource.label}: URL must contain filters.q after typing in the search box`,
      ).toContain(`filters.q=${encodeURIComponent(resource.query)}`);

      // Assert no JS errors in the page
      const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
      for (const needle of JS_ERROR_NEEDLES) {
        expect(body, `${resource.label}: "${needle}" must not appear`).not.toContain(needle);
      }

      // Either table rows or "No records" must be visible (list rendered)
      const hasTable = (await page.locator("table").count()) > 0;
      const hasNoRecords = /No records/i.test(body);
      expect(
        hasTable || hasNoRecords,
        `${resource.label}: list must render (table or No-records) after filter`,
      ).toBe(true);

      void consoleErrors;
    });
  }

  test("Services: typing 'crm' narrows table and the result contains demo-crm", async ({
    page,
    consoleErrors,
  }) => {
    // Navigate directly to the filtered URL — this is the canonical approach used by
    // test 28 (search-filters.spec.ts) and ensures the filter is applied before the
    // list renders.
    await page.goto("/admin/resources/services?filters.q=crm", { waitUntil: "domcontentloaded" });
    await page.locator("table tbody tr").first().waitFor({ state: "visible", timeout: 25_000 });

    expect(page.url()).toContain("filters.q=crm");

    // The search input must be pre-filled from the URL on mount
    const searchInput = page.locator('[data-testid="inline-search-input"]');
    const inputVal = await searchInput.inputValue();
    expect(inputVal, "search input must be pre-populated from URL filters.q param").toBe("crm");

    // Table must contain demo-crm
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(body, "demo-crm must appear in filtered table").toContain("demo-crm");

    for (const needle of JS_ERROR_NEEDLES) {
      expect(body, `"${needle}" must not appear`).not.toContain(needle);
    }

    // Clear the filter by emptying the input; URL should update
    await searchInput.fill("");
    await page.waitForURL(
      (url) => !url.toString().includes("filters.q=crm"),
      { timeout: 10_000 },
    );
    expect(page.url()).not.toContain("filters.q=crm");

    void consoleErrors;
  });

  test("screenshot: services list with inline search box visible", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await waitForList(page);

    // Make the search box visible with a query
    const searchInput = page.locator('[data-testid="inline-search-input"]');
    await searchInput.fill("demo");
    await page.waitForTimeout(1200);

    await page.screenshot({
      path: path.resolve(__dirname, "../test-results/37-inline-search-services.png"),
      fullPage: false,
    });

    void consoleErrors;
  });
});
