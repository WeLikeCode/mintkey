/**
 * Agents page object — create, revoke, and view actions.
 *
 * Source: F-OP-04; T-1.4.3; T-1.9.4.
 *
 * SECURITY NOTE (ADR-0014.4 / Req 5 AC2):
 * The API key is shown exactly ONCE in the create-agent response notice.
 * The key must be captured here — it is never retrievable again.
 */

import { type Page, type Locator } from "@playwright/test";
import { BasePage } from "./base.js";

export class AgentsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  // ── List view ──────────────────────────────────────────
  async gotoList() {
    await this.goto("/admin/resources/agents");
  }

  getRowByName(name: string | RegExp) {
    return this.page.locator("tr").filter({ hasText: name });
  }

  getNewButton() {
    return this.page.getByRole("button", { name: /\+ *new|add agent/i });
  }

  // ── Create agent ───────────────────────────────────────
  async gotoNew() {
    await this.goto("/admin/resources/agents/actions/new");
  }

  async createAgent(data: {
    name: string;
    description?: string;
    mcpEndpoint?: string;
    rateLimitRps?: number;
  }): Promise<{ agentId: string; apiKey: string }> {
    await this.gotoNew();
    // Wait for the form label to be visible rather than networkidle (avoids flakiness under load)
    await this.page.getByLabel("name").waitFor({ state: "visible", timeout: 20_000 });

    await this.page.getByLabel("name").fill(data.name);
    if (data.description) await this.page.getByLabel("description").fill(data.description);
    if (data.mcpEndpoint) await this.page.getByLabel(/mcp.endpoint/i).fill(data.mcpEndpoint);
    if (data.rateLimitRps) await this.page.getByLabel(/rate.limit/i).fill(String(data.rateLimitRps));

    // Wait for the AdminJS API response — API key is in notice.message (Req 5 AC2)
    const [response] = await Promise.all([
      this.page.waitForResponse(
        (r) => r.url().includes("/admin/api/resources/agents/actions/new") && r.request().method() === "POST",
        { timeout: 15_000 }
      ),
      this.page.getByRole("button", { name: /save|create/i }).click(),
    ]);

    let apiKey = "";
    try {
      const body = await response.json() as { notice?: { message?: string }; redirectUrl?: string };
      const noticeMsg = body.notice?.message ?? "";
      const keyMatch = noticeMsg.match(/API key \(shown once\):\s*(\S+)/);
      apiKey = keyMatch?.[1] ?? "";
    } catch {
      // apiKey stays ""
    }

    // The admin-api CREATE response returns a ULID-format id (agent_01KRH...) but the DB
    // primary key is a UUID. The LIST endpoint returns agent_<32hex> format which is what
    // the admin-api write endpoints accept after UUID conversion in the handler.
    // Navigate to the filtered list to get the canonical hex-UUID record id.
    await this.goto(`/admin/resources/agents?filters.q=${encodeURIComponent(data.name)}`);
    await this.page.waitForLoadState("networkidle");

    const row = this.page.locator("tr").filter({ hasText: data.name });
    await row.first().waitFor({ state: "visible", timeout: 15_000 });
    const showLink = await row.first()
      .locator('a[href*="/records/"][href*="/show"]')
      .getAttribute("href");
    const agentId = showLink?.match(/\/records\/([^/]+)\/show/)?.[1] ?? "";

    return { agentId, apiKey };
  }

  // ── Revoke agent ───────────────────────────────────────
  async revokeAgent(agentId: string) {
    await this.goto(`/admin/resources/agents/records/${agentId}/revokeAgent`);
    await this.page.waitForLoadState("networkidle");
    const confirmBtn = this.page.locator('[data-testid="confirm-action-button"]');
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
      await this.page.waitForLoadState("networkidle");
    }
  }

  // ── Show agent detail ──────────────────────────────────
  async gotoShow(agentId: string) {
    await this.goto(`/admin/resources/agents/records/${agentId}/show`);
  }
}
