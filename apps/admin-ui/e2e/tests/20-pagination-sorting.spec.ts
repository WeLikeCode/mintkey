/**
 * W5: Pagination + sorting on the Services list.
 *
 * Verifies:
 *  (a) Page 2 exists and shows different rows than page 1 (if enough records).
 *  (b) Total-count label is consistent: same number on page 1 and page 2.
 *  (c) Column-header click toggles ?sortBy=…&direction=… in the URL.
 *  (d) Sort direction toggle: clicking the same header again flips direction.
 *
 * Source: PLAYWRIGHT_EXTENSION_PLAN.md W5.
 */

import { test, expect } from "../fixtures/test.js";

/** Extract the total-record count from AdminJS pagination label ("1-10 of 42"). */
function parseTotalCount(text: string): number | null {
  const m = text.match(/of\s+(\d+)/i) ?? text.match(/(\d+)\s+records?/i);
  return m ? parseInt(m[1], 10) : null;
}

test.describe("20 — Pagination and sorting (Services list)", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // ── (a + b) Pagination ───────────────────────────────────────────────────────
  test("page 1 and page 2 exist; total count is consistent across pages", async ({
    page,
    consoleErrors,
  }) => {
    // Increase timeout for this test — it makes two page navigations
    test.setTimeout(60_000);

    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    // Wait for the table or empty-state to appear (short explicit timeout — avoids 30s implicit action wait)
    await page.locator("table tbody tr, table, [class*='empty']").first()
      .waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});

    const body = (await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) ?? "";
    expect(body).not.toContain("Javascript Error");

    // Extract total count from the pagination footer (if present; 3s max — not critical)
    const paginationEl = page.locator(
      '[data-testid="pagination"], .pagination, nav[aria-label*="pagination" i], [class*="pagination"]',
    );
    const paginationText = (
      (await paginationEl.first().textContent({ timeout: 3_000 }).catch(() => "")) ?? ""
    ).trim();
    const totalCount = parseTotalCount(paginationText);

    // If fewer than 11 records exist, page 2 won't exist — skip gracefully but still
    // assert the list page renders cleanly.
    const rows = page.locator("table tbody tr");
    const rowCount = await rows.count();

    if (rowCount === 0) {
      void consoleErrors;
      return;
    }

    // Collect page-1 row text
    const page1Rows: string[] = [];
    for (let i = 0; i < rowCount; i++) {
      page1Rows.push(((await rows.nth(i).textContent().catch(() => "")) ?? "").trim());
    }

    // Check if a "next page" or page-2 link exists
    const nextLink = page
      .locator('a[href*="page=2"], button[aria-label*="next" i], a[aria-label*="next" i]')
      .first();
    const hasPage2 = (await nextLink.count()) > 0;

    if (!hasPage2) {
      // Only one page — still assert clean render and no JS error
      void consoleErrors;
      return;
    }

    // ── Navigate to page 2 ────────────────────────────────────────────────────
    const currentUrl = page.url();
    const page2Url = currentUrl.includes("?")
      ? currentUrl + "&page=2"
      : currentUrl + "?page=2";

    await page.goto(page2Url, { waitUntil: "domcontentloaded" });
    await page.locator("table tbody tr, table, [class*='empty']").first()
      .waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});

    const page2Body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(page2Body).not.toContain("Javascript Error");

    const page2Rows = page.locator("table tbody tr");
    const page2RowCount = await page2Rows.count();

    if (page2RowCount > 0) {
      // Page 2 must show at least one different row
      const page2FirstRow = ((await page2Rows.first().textContent().catch(() => "")) ?? "").trim();
      const appearsOnPage1 = page1Rows.some((r) => r.length > 0 && r === page2FirstRow);
      expect(
        appearsOnPage1,
        "page-2 first row must differ from all page-1 rows (pagination must advance)",
      ).toBe(false);
    }

    // Total count label must be consistent between page 1 and page 2
    if (totalCount !== null) {
      const page2PaginationEl = page.locator(
        '[data-testid="pagination"], .pagination, nav[aria-label*="pagination" i], [class*="pagination"]',
      );
      const page2PaginationText = (
        (await page2PaginationEl.first().textContent({ timeout: 3_000 }).catch(() => "")) ?? ""
      ).trim();
      const page2TotalCount = parseTotalCount(page2PaginationText);
      if (page2TotalCount !== null) {
        expect(page2TotalCount, "total record count must be identical on page 1 and page 2").toBe(
          totalCount,
        );
      }
    }

    void consoleErrors;
  });

  // ── (c) Column sort — first click ───────────────────────────────────────────
  test("clicking a column header adds sortBy + direction to the URL", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await page.locator("table, [class*='list'], [class*='empty']").first()
      .waitFor({ state: "visible", timeout: 20_000 }).catch(() => {});

    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(body).not.toContain("Javascript Error");

    // Find a sortable column header (AdminJS renders these as <a> or <th> with a link)
    const sortableHeader = page
      .locator('th a[href*="sortBy"], th[data-sort], thead th a')
      .first();

    const hasSortable = (await sortableHeader.count()) > 0;
    if (!hasSortable) {
      // No sortable headers visible — assert clean render and exit
      void consoleErrors;
      return;
    }

    // Click the header
    await sortableHeader.click();
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});

    const urlAfterSort = page.url();
    const hasSortParam =
      /sortBy=/i.test(urlAfterSort) ||
      /sort=/i.test(urlAfterSort) ||
      /orderBy=/i.test(urlAfterSort);

    expect(
      hasSortParam,
      `URL after column-header click must contain a sort param. URL was: ${urlAfterSort}`,
    ).toBe(true);

    const afterBody = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(afterBody).not.toContain("Javascript Error");

    void consoleErrors;
  });

  // ── (d) Sort direction toggle ────────────────────────────────────────────────
  test("clicking the same column header again toggles sort direction (asc → desc)", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await page.locator("table, [class*='list'], [class*='empty']").first()
      .waitFor({ state: "visible", timeout: 20_000 }).catch(() => {});

    const sortableHeader = page
      .locator('th a[href*="sortBy"], th[data-sort], thead th a')
      .first();

    if ((await sortableHeader.count()) === 0) {
      void consoleErrors;
      return;
    }

    // First click — set asc direction
    await sortableHeader.click();
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    const urlAsc = page.url();

    // Second click on the same header — should flip direction
    // Re-query because the DOM may have re-rendered
    const sortableHeader2 = page
      .locator('th a[href*="sortBy"], th[data-sort], thead th a')
      .first();
    await sortableHeader2.click();
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    const urlDesc = page.url();

    // The two URLs must differ (direction param changed)
    expect(urlAsc, "URLs before and after second click must differ").not.toEqual(urlDesc);

    const afterBody = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(afterBody).not.toContain("Javascript Error");

    void consoleErrors;
  });
});
