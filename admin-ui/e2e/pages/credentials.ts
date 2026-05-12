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

import { type Page, type Locator, type APIResponse } from "@playwright/test";
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
    await this.gotoList();

    // Click "Register Credential" button on the list page
    const registerBtn = this.page.getByRole("button", { name: /register credential/i });
    await registerBtn.click();

    // Fill the form
    if (options.serviceId) {
      const serviceSelect = this.page.locator("select").filter({ hasText: /service/i });
      await serviceSelect.selectOption(options.serviceId);
    }
    if (options.authScheme) {
      const schemeSelect = this.page.locator("select").filter({ hasText: /auth scheme/i });
      await schemeSelect.selectOption(options.authScheme);
    }
    if (options.plaintext) {
      await this.getPlaintextField().fill(options.plaintext);
    }

    // Capture the notice — this is the ONLY place the plaintext key may appear
    let noticeText = "";
    let plaintextKey: string | undefined;

    const [response] = await Promise.all([
      this.page.waitForResponse((r) => r.url().includes("/credentials") && r.request().method() === "POST", { timeout: 10_000 }),
      this.page.getByRole("button", { name: /save|register/i }).click(),
    ]);

    // The API response body may contain the plaintext key
    try {
      const body = await response.json();
      if (body.plaintext_key) plaintextKey = body.plaintext_key;
    } catch {
      // response may not be JSON
    }

    // Also check the AdminJS notice banner
    const notice = this.page.locator(".alert-success, .notice, [role='alert']").first();
    if (await notice.isVisible()) {
      noticeText = (await notice.textContent()) ?? "";
    }

    return {
      success: true,
      plaintext: plaintextKey,
      noticeText,
    };
  }

  /**
   * Get the plaintext input field (only present on the credential form).
   */
  private getPlaintextField(): Locator {
    return this.page.getByLabel(/plaintext|secret|password|credential/i, { exact: false });
  }

  // ── Rotate credential ──────────────────────────────────
  async rotateCredential(credentialId: string, newPlaintext: string): Promise<string> {
    // Find the row and click "Rotate"
    const row = this.page.locator("tr").filter({ has: this.page.locator(`[data-id="${credentialId}"]`) });
    const rotateBtn = row.getByRole("button", { name: /rotate/i });
    await rotateBtn.click();

    // Fill new plaintext if prompted
    const plaintextField = this.getPlaintextField();
    if (await plaintextField.isVisible()) {
      await plaintextField.fill(newPlaintext);
    }

    // Capture the new key from the notice
    const [response] = await Promise.all([
      this.page.waitForResponse((r) => r.url().includes("/credentials") && r.request().method() === "POST", { timeout: 10_000 }),
      this.page.getByRole("button", { name: /save|rotate/i }).click(),
    ]);

    let newKey: string | undefined;
    try {
      const body = await response.json();
      if (body.plaintext_key) newKey = body.plaintext_key;
    } catch {
      // response may not be JSON
    }

    return newKey ?? "";
  }
}