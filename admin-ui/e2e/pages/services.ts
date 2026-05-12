/**
 * Services page object — list, new, edit, show, and test actions.
 *
 * Source: F-OP-02; T-1.2.3.
 */

import { type Page, type Locator, type APIResponse, type Response } from "@playwright/test";
import { BasePage } from "./base.js";

export class ServicesPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  // ── List view ──────────────────────────────────────────
  async gotoList() {
    await this.goto("/admin/resources/services");
  }

  getRowByName(name: string | RegExp) {
    return this.page.locator("tr").filter({ hasText: name });
  }

  getNewButton() {
    return this.page.getByRole("button", { name: /\+ *new|add service/i });
  }

  // ── New / create ───────────────────────────────────────
  async gotoNew() {
    await this.goto("/admin/resources/services/new");
  }

  getFormField(name: string | RegExp) {
    return this.page.getByLabel(name, { exact: false });
  }

  /**
   * Fill the "new service" form and submit.
   * Waits for redirect back to list.
   */
  async createService(data: {
    name: string;
    slug?: string;
    baseUrl?: string;
    authScheme?: string;
    description?: string;
    openapiUrl?: string;
  }) {
    await this.gotoNew();
    await this.getFormField("name").fill(data.name);
    if (data.slug) await this.getFormField("slug").fill(data.slug);
    if (data.baseUrl) await this.getFormField("base url").fill(data.baseUrl);
    if (data.authScheme) {
      const schemeSelect = this.page.locator("select").filter({ hasText: /api_key|bearer|basic|oauth/i });
      await schemeSelect.selectOption(data.authScheme);
    }
    if (data.description) await this.getFormField("description").fill(data.description);
    if (data.openapiUrl) await this.getFormField("openapi url").fill(data.openapiUrl);

    const [response] = await Promise.all([
      this.page.waitForResponse((r) => r.url().includes("/admin-api/v1/tenants") && r.request().method() === "POST", { timeout: 10_000 }),
      this.getFormField("save").click(),
    ]);
    return response;
  }

  // ── Show / detail view ─────────────────────────────────
  async gotoShow(serviceId: string) {
    await this.goto(`/admin/resources/services/${serviceId}/show`);
  }

  // ── Edit ───────────────────────────────────────────────
  async gotoEdit(serviceId: string) {
    await this.goto(`/admin/resources/services/${serviceId}/edit`);
  }

  async updateService(serviceId: string, updates: { name?: string; baseUrl?: string }) {
    await this.gotoEdit(serviceId);
    if (updates.name) await this.getFormField("name").fill(updates.name);
    if (updates.baseUrl) await this.getFormField("base url").fill(updates.baseUrl);

    await Promise.all([
      this.page.waitForResponse((r) => r.url().includes(`/services/${serviceId}`) && r.request().method() === "PATCH"),
      this.getFormField("save").click(),
    ]);
  }

  // ── Delete ─────────────────────────────────────────────
  async deleteService(serviceId: string) {
    await this.gotoShow(serviceId);
    const deleteBtn = this.page.getByRole("button", { name: /delete/i });
    await deleteBtn.click();
    await this.confirmDialog(true);
  }

  // ── Test connection action ─────────────────────────────
  async testService(serviceId: string) {
    await this.gotoShow(serviceId);
    const testBtn = this.page.getByRole("button", { name: /test connection/i });

    const [response] = await Promise.all([
      this.page.waitForResponse((r) => r.url().includes("/services/") && r.url().includes("/test"), { timeout: 10_000 }),
      testBtn.click(),
    ]);
    return response;
  }

  // ── Navigate to Credentials tab from Service detail ────
  async gotoCredentialsTab(serviceId: string) {
    await this.gotoShow(serviceId);
    const tab = this.page.getByRole("tab", { name: /credential/i });
    await tab.click();
  }
}