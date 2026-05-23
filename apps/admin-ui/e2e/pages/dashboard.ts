/**
 * Dashboard page object.
 */

import { type Page, type Locator } from "@playwright/test";
import { BasePage } from "./base.js";

export class DashboardPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  /**
   * Get all navigation links in the sidebar.
   */
  getNavLinks() {
    return this.page.locator("nav a, .sidebar a, .admin-nav a");
  }

  /**
   * Navigate to a specific resource by clicking the sidebar.
   */
  async gotoResource(name: string) {
    const link = this.getNavLinks().filter({ hasText: name });
    await link.click();
    await this.page.waitForLoadState("domcontentloaded");
  }
}