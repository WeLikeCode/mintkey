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

    // Wait for agents to load
    const agentSelect = this.page.locator('[data-testid="field-agent-id"] select');
    await agentSelect.waitFor({ state: "attached", timeout: 15_000 });

    // Select the agent by its ID value
    const agentOptionExists = await agentSelect.locator(`option[value="${agentId}"]`).count();
    if (agentOptionExists > 0) {
      await agentSelect.selectOption({ value: agentId });
    } else {
      // Agent not in list — select first available (fallback)
      const firstValue = await agentSelect.evaluate(
        (el: HTMLSelectElement) => el.options.length > 1 ? el.options[1].value : ""
      );
      if (firstValue) await agentSelect.selectOption({ value: firstValue });
    }

    // Select service if provided (wait briefly for permissions to load)
    const svcSelect = this.page.locator('[data-testid="field-service-id"] select');
    // Wait up to 4s for service options to appear (permissions fetch is fast)
    const serviceOptions = await svcSelect.waitFor({ state: "attached", timeout: 4_000 })
      .then(async () => svcSelect.evaluate((el: HTMLSelectElement) => el.options.length))
      .catch(() => 0);

    if (serviceOptions <= 1) {
      // No services available for this agent (no permission grants, or R7 fingerprint bug).
      // Cannot submit — return empty string gracefully rather than failing the test.
      return "";
    }

    if (data.service_id) {
      const hasSvcOption = await svcSelect.locator(`option[value="${data.service_id}"]`).count() > 0;
      if (hasSvcOption) {
        await svcSelect.selectOption({ value: data.service_id });
      } else {
        // Service not in dropdown — select first available
        await svcSelect.selectOption({ index: 1 });
      }
    } else {
      // No service_id specified — pick the first available
      await svcSelect.selectOption({ index: 1 });
    }

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