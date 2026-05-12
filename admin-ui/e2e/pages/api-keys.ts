/**
 * API Keys page object — create, revoke, rotate.
 *
 * Source: T-1.5.2; long-lived API keys tasks.
 *
 * Plaintext key is shown exactly once at creation (ADR-0018 §1.3).
 */

import { type Page, type Locator } from "@playwright/test";
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

  getCreateApiKeyButton() {
    return this.page.getByRole("button", { name: /create api key/i });
  }

  /**
   * Create an API key for a given agent.
   * Returns the plaintext key captured from the one-time notice.
   */
  async createApiKey(agentId: string, data: {
    service_id?: string;
    allowed_actions?: string;
    constraints?: string;
    expires_at?: string;
  }): Promise<string> {
    await this.gotoList();
    await this.getCreateApiKeyButton().click();

    // Fill agent_id
    if (agentId) {
      const agentSelect = this.page.locator("select").filter({ hasText: /agent/i });
      // May need to type the agent ID
      await agentSelect.fill(agentId);
    }

    if (data.service_id) {
      const serviceSelect = this.page.locator("select").filter({ hasText: /service/i });
      await serviceSelect.fill(data.service_id);
    }
    if (data.allowed_actions) {
      await this.page.getByLabel("allowed actions").fill(data.allowed_actions);
    }
    if (data.constraints) {
      await this.page.getByLabel("constraints").fill(data.constraints);
    }
    if (data.expires_at) {
      await this.page.getByLabel("expires at").fill(data.expires_at);
    }

    // Capture key from notice
    const [notice] = await Promise.all([
      this.page.waitForSelector(".alert-success, .notice:has-text('API key')", { timeout: 10_000 }),
      this.page.getByRole("button", { name: /save|create/i }).click(),
    ]);

    const noticeText = await notice.textContent();
    const keyMatch = noticeText?.match(/shown once.*:\s*([A-Za-z0-9_-]+)/);
    return keyMatch?.[1] ?? "";
  }

  /**
   * Revoke an API key by clicking the Revoke button on its row.
   */
  async revokeApiKey(keyId: string) {
    const row = this.getRowByKeyFingerprint(new RegExp(keyId));
    // The row may show key_fingerprint truncated; use partial match
    const revokeBtn = row.locator("a").filter({ hasText: /revoke/i });
    await revokeBtn.click();
  }

  /**
   * Rotate an API key — creates a new key while the old one stays active.
   * Returns the new plaintext key.
   */
  async rotateApiKey(keyId: string): Promise<string> {
    const row = this.getRowByKeyFingerprint(new RegExp(keyId));
    const rotateBtn = row.locator("a").filter({ hasText: /rotate/i });

    const [notice] = await Promise.all([
      this.page.waitForSelector(".alert-success, .notice:has-text('key')", { timeout: 10_000 }),
      rotateBtn.click(),
    ]);

    const noticeText = await notice.textContent();
    const keyMatch = noticeText?.match(/shown once.*:\s*([A-Za-z0-9_-]+)/);
    return keyMatch?.[1] ?? "";
  }
}