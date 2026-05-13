/**
 * E2E test: PlatformAdmin sees Tenants list with ≥1 row (t_default).
 *
 * Verifies that:
 *   1. The bootstrap operator (PlatformAdmin) can navigate to /admin/resources/tenants.
 *   2. The list renders ≥1 row.
 *   3. The text "t_default" appears in the page (the default tenant slug).
 *
 * Root cause fixed: X-Platform-Admin: true header was not forwarded to admin-api
 * from RestResource.find() — so /v1/tenants returned 403 for PlatformAdmin.
 *
 * Source: fix-tenants-403 chunk; ADR-0016.3.
 *
 * Run: MINTKEY_ADMIN_PASSWORD="$(cat ../data/bootstrap-secrets/admin_password)" \
 *        npx playwright test tests/e2e/tenants-platform-admin.spec.ts
 */

import { test, expect, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const ADMIN_EMAIL = process.env.MINTKEY_ADMIN_USER ?? "admin@mintkey.internal";
const ADMIN_PASSWORD = process.env.MINTKEY_ADMIN_PASSWORD ?? "";

const SCREENSHOT_DIR = path.resolve(process.cwd(), "test-results", "tenants-pa-screenshots");
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

test("PlatformAdmin sees Tenants list with ≥1 row including t_default", async ({ page }) => {
  await login(page);

  // Navigate to tenants list
  await page.goto("/admin/resources/tenants");
  await page.waitForLoadState("networkidle", { timeout: 30_000 });

  // Take screenshot for reviewer
  const screenshotPath = path.join(SCREENSHOT_DIR, "tenants-list.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  // Assert no JS error box
  const jsErrorText = await page.locator("text=Javascript Error").count();
  expect(jsErrorText, "No Javascript Error should appear on the page").toBe(0);

  // Assert at least one table row visible (AdminJS renders <tbody> with <tr> rows)
  const tableRows = page.locator("table tbody tr");
  const rowCount = await tableRows.count();
  expect(rowCount, `Expected ≥1 row in tenants table, got ${rowCount}`).toBeGreaterThanOrEqual(1);

  // Assert the default tenant slug appears
  const pageContent = await page.content();
  expect(pageContent, "Expected t_default to appear in the tenants list").toContain("t_default");
});
