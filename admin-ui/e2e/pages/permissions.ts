/**
 * Permissions page object — grant and revoke.
 */

import { type Page, type Locator } from "@playwright/test";
import { BasePage } from "./base.js";

export class PermissionsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async gotoList() {
    await this.goto("/admin/resources/permission_grants");
  }

  getGrantButton() {
    return this.page.getByRole("button", { name: /grant/i });
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
    await this.gotoList();
    await this.getGrantButton().click();

    // Fill form fields
    await this.page.getByLabel("agent id").fill(data.agent_id);
    await this.page.getByLabel("service id").fill(data.service_id);
    await this.page.getByLabel("action").fill(data.action);
    if (data.constraints) {
      await this.page.getByLabel("constraints").fill(data.constraints);
    }

    await this.page.getByRole("button", { name: /save|grant/i }).click();

    // Wait for success notice
    await this.page.waitForSelector(".alert-success", { timeout: 10_000 });
  }

  /**
   * Revoke a permission by finding its row and clicking the delete/revoke action.
   */
  async revokePermission(permissionId: string) {
    const row = this.page.locator("tr").filter({ hasText: permissionId });
    const deleteBtn = row.locator("a").filter({ hasText: /delete|revoke/i });
    await deleteBtn.click();
    await this.confirmDialog(true);
  }
}