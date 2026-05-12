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
   * Create an API key for a given agent.
   * Returns the plaintext key captured from the one-time API response notice.
   */
  async createApiKey(agentId: string, data: {
    service_id?: string;
    allowed_actions?: string;
    constraints?: string;
    expires_at?: string;
  }): Promise<string> {
    // Navigate directly to the new action form (built-in form, works without custom component)
    await this.goto("/admin/resources/service_api_keys/actions/new");
    await this.page.waitForLoadState("networkidle");

    await this.page.getByLabel(/agent.?id/i).fill(agentId);

    if (data.service_id) {
      await this.page.getByLabel(/service.?id/i).fill(data.service_id);
    }
    if (data.allowed_actions) {
      await this.page.getByLabel(/allowed.actions/i).fill(data.allowed_actions);
    }
    if (data.constraints) {
      await this.page.getByLabel("constraints").fill(data.constraints);
    }
    if (data.expires_at) {
      await this.page.getByLabel(/expires.at/i).fill(data.expires_at);
    }

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/service_api_keys/actions/new") && r.request().method() === "POST",
        { timeout: 15_000 }
      ),
      this.page.getByRole("button", { name: /save|create/i }).click(),
    ]);

    let plaintext = "";
    try {
      const body = await response.json() as { notice?: { message?: string } };
      const noticeText = body.notice?.message ?? "";
      const keyMatch = noticeText.match(/shown once[^:]*:\s*(\S+)/i);
      if (keyMatch) plaintext = keyMatch[1];
    } catch {}

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