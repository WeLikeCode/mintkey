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
   * Pick an option by wire id in the agent/service combobox of the permission form.
   * `search` is what gets typed to narrow the server-side list (agents/services are searched by
   * name, not by wire id); it defaults to the wire id.
   */
  private async pickCombobox(kind: "agent" | "service", wireId: string, search: string = wireId) {
    const input = this.page.locator(`[data-testid="${kind}-combobox-input"]`);
    await input.waitFor({ state: "visible", timeout: 15_000 });
    await input.click();
    await input.fill(search);
    const option = this.page.locator(`[data-testid="${kind}-combobox-dropdown"] li[data-value="${wireId}"]`);
    await option.waitFor({ state: "visible", timeout: 15_000 });
    await option.click();
  }

  /**
   * Grant a permission to an agent.
   */
  async grantPermission(data: {
    agent_id: string;
    service_id: string;
    agent_search?: string;
    service_search?: string;
    action: string;
    constraints?: string; // JSON string
  }) {
    // Navigate directly — AdminJS "new" action button is a link, not a <button>
    await this.goto("/admin/resources/permission_grants/actions/new");
    await this.page.waitForLoadState("networkidle");

    // agent_id / service_id are async comboboxes (UX-A): type the id, click the matching option.
    // (The old plain-text "agent id" / "service id" inputs no longer exist.)
    await this.pickCombobox("agent", data.agent_id, data.agent_search);
    await this.pickCombobox("service", data.service_id, data.service_search);
    await this.page.locator("#action").fill(data.action);
    if (data.constraints) {
      await this.page.getByLabel("constraints").fill(data.constraints);
    }

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/permission_grants/actions/new") && r.request().method() === "POST",
        { timeout: 10_000 }
      ),
      this.page.locator('[data-testid="button-save"]').click(),
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