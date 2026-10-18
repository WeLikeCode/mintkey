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

import { type Page } from "@playwright/test";
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
  /**
   * Register a credential through the real CredentialNewForm (data-testid selectors).
   *
   * The AdminJS default credentials "new" form (free-text auth-scheme + "plaintext" inputs, a
   * "Save/Register" button, a "shown once" notice) was replaced by CredentialNewForm: the service
   * is locked from `?service_id=`, the auth scheme is a native <select>, the secret is a password
   * input (`field-input-value`) and success is an in-page banner followed by a redirect to the list.
   * The plaintext is never echoed back; the security assertions live in the callers (list/show
   * pages must not contain it).
   */
  async registerCredential(options: {
    serviceId: string;
    authScheme: string;
    plaintext: string;
  }): Promise<{ success: boolean; plaintext?: string; noticeText: string }> {
    await this.goto(`/admin/resources/credentials/actions/new?service_id=${encodeURIComponent(options.serviceId)}`);
    await this.page.locator("[data-testid='credential-new-form']").waitFor({ state: "visible", timeout: 15_000 });

    await this.page.locator("[data-testid='field-select-auth_scheme']").selectOption(options.authScheme);
    await this.page.locator("[data-testid='field-input-value']").fill(options.plaintext);

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/credentials/actions/new") && r.request().method() === "POST",
        { timeout: 10_000 }
      ),
      this.page.locator("[data-testid='credential-new-submit']").click(),
    ]);

    let noticeText = "";
    let failed = !response.ok();
    try {
      const body = await response.json() as { notice?: { message?: string; type?: string } };
      noticeText = body.notice?.message ?? "";
      if (body.notice?.type === "error") failed = true;
    } catch {
      // response may not be JSON
    }
    if (!failed) {
      await this.page.locator("[data-testid='credential-new-form-success']").waitFor({ state: "visible", timeout: 10_000 });
    }

    return { success: !failed, noticeText };
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