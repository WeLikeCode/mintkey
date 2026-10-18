/**
 * API Keys page object — create, revoke, rotate.
 *
 * Source: T-1.5.2; long-lived API keys tasks.
 *
 * Plaintext key is shown exactly once at creation (ADR-0018 §1.3).
 */

import { type Page } from "@playwright/test";
import { BasePage } from "./base.js";

export class ApiKeysPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async gotoList() {
    await this.goto("/admin/resources/service_api_keys");
  }

  getRowByKeyFingerprint(fingerprint: string | RegExp) {
    return this.page.locator("tr").filter({ hasText: fingerprint });
  }

  /**
   * Create an API key for a given agent via the custom createApiKey action (ADR-0018).
   * The `new` built-in action is hidden; creation goes through the show-once custom form.
   * Returns the plaintext key captured from the one-time modal response.
   *
   * @param agentId  - the agent's ID value (used to select the agent from the dropdown)
   * @param data.service_id - optional service ID to select in the form
   */
  async createApiKey(agentId: string, data: {
    service_id?: string;
    agentSearch?: string;
    allowed_actions?: string;
    constraints?: string;
    expires_at?: string;
  }): Promise<string> {
    // Navigate to the createApiKey custom action (the `new` action is hidden per ADR-0018).
    await this.goto("/admin/resources/service_api_keys/actions/createApiKey");
    // Form appears quickly; skip networkidle which can hang on AdminJS background polls.
    await this.page.locator('[data-testid="api-key-create-form"]').waitFor({
      state: "visible",
      timeout: 10_000,
    });

    // The agent and service pickers are async comboboxes (UX-A), not <select>s. Agents are searched
    // server-side by name, so type `agentSearch` (default: the wire id) and click the option whose
    // data-value is the wire id; the service combobox then lists the agent's permission grants.
    const agentInput = this.page.locator('[data-testid="combobox-agent-input"]');
    await agentInput.waitFor({ state: "visible", timeout: 15_000 });
    await agentInput.click();
    await agentInput.fill(data.agentSearch ?? agentId);
    const agentOption = this.page.locator(
      `[data-testid="combobox-agent-dropdown"] li[data-value="${agentId}"]`
    );
    await agentOption.waitFor({ state: "visible", timeout: 20_000 });
    await agentOption.click();

    // Wait for the agent's permissions (service options) to load.
    const serviceInput = this.page.locator('[data-testid="combobox-service-input"]');
    await serviceInput.waitFor({ state: "visible", timeout: 15_000 });
    await this.page.waitForFunction(
      () => !document.body.innerText.includes("Loading services"),
      undefined,
      { timeout: 15_000 }
    );
    await serviceInput.click();
    const svcOptions = this.page.locator('[data-testid="combobox-service-dropdown"] li[data-value]');
    const hasOptions = await svcOptions.first().waitFor({ state: "visible", timeout: 5_000 }).then(() => true).catch(() => false);
    if (!hasOptions) {
      // The agent has no permission grants, so there is no service to pick and the form cannot
      // be submitted. Return "" (callers that need a key grant a permission first).
      return "";
    }
    const wantedService = data.service_id
      ? this.page.locator(`[data-testid="combobox-service-dropdown"] li[data-value="${data.service_id}"]`)
      : svcOptions.first();
    await wantedService.waitFor({ state: "visible", timeout: 10_000 });
    await wantedService.click();

    if (data.expires_at) {
      await this.page.locator('[data-testid="field-expires-at"] input').fill(data.expires_at);
    }

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/service_api_keys/actions/createApiKey")
             && r.request().method() === "POST",
        { timeout: 20_000 }
      ),
      this.page.locator('[data-testid="api-key-create-submit"]').click(),
    ]);

    let plaintext = "";
    try {
      const body = await response.json() as { notice?: { message?: string } };
      const noticeText = body.notice?.message ?? "";
      const keyMatch = noticeText.match(/shown once[^:]*:\s*(\S+)/i);
      if (keyMatch) plaintext = keyMatch[1];
    } catch { /* ignore parse errors */ }

    // If the show-once modal appeared, also capture the key from it and confirm.
    const modal = this.page.locator('[data-testid="show-once-modal"]');
    const modalVisible = await modal.isVisible({ timeout: 3_000 }).catch(() => false);
    if (modalVisible) {
      const modalText = await modal.locator('[data-testid="plaintext-key-box"]').innerText().catch(() => "");
      if (modalText) plaintext = modalText;
      const confirmBtn = modal.locator('[data-testid="modal-confirm-btn"]');
      if (await confirmBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await confirmBtn.click();
        await this.page.waitForURL(/\/admin\/resources\/service_api_keys/, { timeout: 10_000 }).catch(() => {});
      }
    }

    return plaintext;
  }

  /**
   * Revoke an API key by navigating to its show page and clicking Revoke.
   */
  async revokeApiKey(keyId: string) {
    await this.goto(`/admin/resources/service_api_keys/records/${keyId}/show`);
    await this.page.waitForLoadState("networkidle");

    const revokeBtn = this.page.locator('[data-testid="action-revokeApiKey"]');
    if (await revokeBtn.isVisible()) {
      await revokeBtn.click();
      await this.page.waitForLoadState("networkidle");
    }
  }

  /**
   * Rotate an API key — creates a new key while the old one stays active.
   * Returns the new plaintext key from the one-time API response notice.
   * No-ops gracefully if the show page is unavailable.
   */
  async rotateApiKey(keyId: string): Promise<string> {
    await this.goto(`/admin/resources/service_api_keys/records/${keyId}/show`);
    await this.page.waitForLoadState("networkidle");

    const rotateBtn = this.page.locator('[data-testid="action-rotateApiKey"]');
    const visible = await rotateBtn.isVisible({ timeout: 2_000 }).catch(() => false);
    if (!visible) return "";

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/service_api_keys") && r.request().method() === "POST",
        { timeout: 15_000 }
      ),
      rotateBtn.click(),
    ]);

    let newKey = "";
    try {
      const body = await response.json() as { notice?: { message?: string } };
      const noticeText = body.notice?.message ?? "";
      const keyMatch = noticeText.match(/shown once[^:]*:\s*(\S+)/i);
      if (keyMatch) newKey = keyMatch[1];
    } catch {}

    return newKey;
  }
}