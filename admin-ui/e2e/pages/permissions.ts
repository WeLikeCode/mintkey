/**
 * Permissions page object — grant and revoke.
 */

import { type Page } from "@playwright/test";
import { BasePage } from "./base.js";

export class PermissionsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async gotoList() {
    await this.goto("/admin/resources/permission_grants");
  }

  /**
   * Grant a permission to an agent.
   */
  async grantPermission(data: {
    agent_id: string;
    service_id: string;
    action: string;
    constraints?: string; // JSON string
  }) {
    // Navigate directly — AdminJS "new" action button is a link, not a <button>
    await this.goto("/admin/resources/permission_grants/actions/new");
    await this.page.waitForLoadState("networkidle");

    await this.page.getByLabel(/agent.?id/i).fill(data.agent_id);
    await this.page.getByLabel(/service.?id/i).fill(data.service_id);
    await this.page.getByLabel("action").fill(data.action);
    if (data.constraints) {
      await this.page.getByLabel("constraints").fill(data.constraints);
    }

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/permission_grants/actions/new") && r.request().method() === "POST",
        { timeout: 10_000 }
      ),
      this.page.getByRole("button", { name: /save|grant/i }).click(),
    ]);

    // AdminJS 7 notices render inside [data-testid="notice-wrapper"]
    await this.page.waitForSelector('[data-testid="notice-wrapper"]', { timeout: 10_000 }).catch(() => {});
  }

  /**
   * Revoke a permission by navigating to its show page and confirming the delete modal.
   * No-ops gracefully if the show page is unavailable (permissions have no list GET endpoint).
   */
  async revokePermission(permissionId: string) {
    await this.goto(`/admin/resources/permission_grants/records/${permissionId}/show`);
    await this.page.waitForLoadState("networkidle");

    const deleteBtn = this.page.locator('[data-testid="action-delete"]');
    const visible = await deleteBtn.isVisible({ timeout: 2_000 }).catch(() => false);
    if (!visible) return;

    await deleteBtn.click();
    // AdminJS 7 opens a React modal (not window.confirm) for guarded actions
    const confirmBtn = this.page.getByRole("button", { name: /^confirm$/i });
    await confirmBtn.waitFor({ state: "visible", timeout: 5_000 });
    await confirmBtn.click();
    await this.page.waitForLoadState("networkidle");
  }
}