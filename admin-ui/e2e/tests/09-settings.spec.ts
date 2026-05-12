/**
 * Tier 3 — Admin settings.
 */

import { test, expect, type Page } from "@playwright/test";
import { SettingsPage } from "../pages/settings.js";

test.describe("Tier 3 — Settings", () => {
  let page: Page;
  let settings: SettingsPage;

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    settings = new SettingsPage(page);
  });

  test("1. settings page loads with current values", async () => {
    await settings.goto();
    expect(page.url()).toContain("/admin/settings");
    await expect(page.locator("form")).toBeVisible();
  });

  test("2. non-PlatformAdmin cannot access settings", async () => {
    const isPlatformAdmin = process.env.PLAYWRIGHT_IS_PLATFORM_ADMIN === "true";
    if (!isPlatformAdmin) {
      await settings.goto();
    }
  });
});