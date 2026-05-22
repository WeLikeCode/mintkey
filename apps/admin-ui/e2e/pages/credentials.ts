/**
 * Credentials page object — register, rotate, and view actions.
 *
 * Source: T-1.3.4; T-1.8.4; F-OP-03.
 *
 * SECURITY NOTE (ADR-0014.4 / S-SEC-1):
 * The plaintext credential is shown exactly ONCE in the API response.
 * Playwright must capture it from that response — it is never stored in
 * the UI list or show views.
 */

import { type Page, type Locator } from "@playwright/test";
import { BasePage } from "./base.js";

export class CredentialsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  // ── List view ──────────────────────────────────────────
  async gotoList() {
    await this.goto("/admin/resources/credentials");
  }

  getRowByName(name: string | RegExp) {
    return this.page.locator("tr").filter({ hasText: name });
  }

  // ── Register credential (new action) ───────────────────
  async registerCredential(options: {
    serviceId: string;
    authScheme: string;
    plaintext: string;
  }): Promise<{ success: boolean; plaintext?: string; noticeText: string }> {
    // Navigate directly — AdminJS "new" action button is a link, not a <button>
    await this.goto("/admin/resources/credentials/actions/new");

    const authSchemeField = this.page.getByLabel(/auth.scheme/i);
    if (await authSchemeField.isVisible()) {
      await authSchemeField.fill(options.authScheme);
    }
    const plaintextField = this.getPlaintextField();
    if (await plaintextField.isVisible()) {
      await plaintextField.fill(options.plaintext);
    }

    // Capture the notice — this is the ONLY place the plaintext key may appear
    let noticeText = "";
    let plaintextKey: string | undefined;

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/credentials/actions/new") && r.request().method() === "POST",
        { timeout: 10_000 }
      ),
      this.page.getByRole("button", { name: /save|register/i }).click(),
    ]);

    try {
      const body = await response.json() as { notice?: { message?: string } };
      noticeText = body.notice?.message ?? "";
      const keyMatch = noticeText.match(/shown once[^:]*:\s*(\S+)/i);
      if (keyMatch) plaintextKey = keyMatch[1];
    } catch {
      // response may not be JSON
    }

    return { success: true, plaintext: plaintextKey, noticeText };
  }

  /**
   * Get the plaintext input field (only present on the credential form).
   */
  private getPlaintextField(): Locator {
    return this.page.getByLabel(/plaintext|secret|password|credential/i, { exact: false });
  }

  // ── Rotate credential ──────────────────────────────────
  async rotateCredential(credentialId: string, _newPlaintext: string): Promise<string> {
    await this.goto(`/admin/resources/credentials/records/${credentialId}/show`);
    const rotateBtn = this.page.locator('[data-testid="action-rotateCredential"]');
    await rotateBtn.waitFor({ state: "visible", timeout: 15_000 });

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/credentials") && r.request().method() === "POST",
        { timeout: 10_000 }
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