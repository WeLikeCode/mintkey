/**
 * Tenants page object — list, create, edit (PlatformAdmin only).
 *
 * Source: T-1.12.4; ADR-0016.3.
 */

import { type Page, type Locator } from "@playwright/test";
import { BasePage } from "./base.js";

export class TenantsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async gotoList() {
    await this.goto("/admin/resources/tenants");
  }

  getNewButton() {
    return this.page.getByRole("button", { name: /\+ *new|add tenant/i });
  }

  async gotoNew() {
    await this.goto("/admin/resources/tenants/actions/new");
  }

  /**
   * Create a new tenant.
   */
  async createTenant(data: {
    slug: string;
    display_name: string;
    isolation_mode?: string;
  }) {
    await this.gotoNew();
    await this.page.getByLabel("slug").fill(data.slug);
    await this.page.getByLabel("display name").fill(data.display_name);
    if (data.isolation_mode) {
      await this.page.locator("select").filter({ hasText: /isolation/i }).selectOption(data.isolation_mode);
    }

    await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/tenants/actions/new") && r.request().method() === "POST",
        { timeout: 10_000 }
      ),
      this.page.getByRole("button", { name: /save|create/i }).click(),
    ]);
  }

  /**
   * Get slug from the URL when on show/edit page.
   */
  tenantSlugFromUrl(): Promise<string | null> {
    return this.page.locator("td, dd").filter({ hasText: /^[a-z0-9_-]+$/ }).first().textContent();
  }

  /**
   * "All tenants" toggle — appears as a query param link ?all_tenants=true.
   */
  async enablePlatformAdminView() {
    await this.page.goto(`${this.baseURL}/admin/resources/tenants?all_tenants=true`);
  }
}