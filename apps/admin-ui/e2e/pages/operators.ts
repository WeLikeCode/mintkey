/**
 * Operators page object — list + promote (PlatformAdmin only).
 *
 * Operator management is platform-admin-gated (mirrors the Tenants page).
 * Promotion creates an `operators` row by email; admin-api makes no Keycloak
 * call — oidc_sub binds lazily on first OIDC login (ADR-0031 D3).
 *
 * Source: operator-management OpenSpec change; ADR-0031.
 */

import { type Page, type Response } from "@playwright/test";
import { BasePage } from "./base.js";

export class OperatorsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  // ── List view ──────────────────────────────────────────
  async gotoList() {
    await this.goto("/admin/resources/operators");
  }

  getNewButton() {
    return this.page.getByRole("button", { name: /\+ *new|add operator/i });
  }

  getRowByEmail(email: string | RegExp) {
    return this.page.locator("tr").filter({ hasText: email });
  }

  // ── Promote operator ───────────────────────────────────
  async gotoNew() {
    await this.goto("/admin/resources/operators/actions/new");
  }

  /**
   * Promote (create) an operator by email into a home tenant.
   * Returns the AdminJS `new` action POST response so callers can read the notice.
   */
  async promoteOperator(data: {
    email: string;
    tenantId: string;
    displayName?: string;
  }): Promise<Response> {
    await this.gotoNew();
    // Wait for the form to render rather than networkidle (avoids flakiness).
    await this.page.getByLabel("email").waitFor({ state: "visible", timeout: 20_000 });

    await this.page.getByLabel("email").fill(data.email);
    await this.page.getByLabel(/home tenant/i).fill(data.tenantId);
    if (data.displayName) {
      await this.page.getByLabel(/display name/i).fill(data.displayName);
    }

    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) =>
          r.url().includes("/admin/api/resources/operators/actions/new") &&
          r.request().method() === "POST",
        { timeout: 15_000 }
      ),
      this.page.getByRole("button", { name: /save|create/i }).click(),
    ]);

    await this.page.waitForLoadState("networkidle");
    return response;
  }
}
