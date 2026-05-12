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
    await this.goto("/admin/resources/agents/new");
  }

  async createAgent(data: {
    name: string;
    description?: string;
    mcpEndpoint?: string;
    rateLimitRps?: number;
  }): Promise<{ agentId: string; apiKey: string }> {
    await this.gotoNew();

    await this.page.getByLabel("name").fill(data.name);
    if (data.description) await this.page.getByLabel("description").fill(data.description);
    if (data.mcpEndpoint) await this.page.getByLabel("mcp endpoint").fill(data.mcpEndpoint);
    if (data.rateLimitRps) await this.page.getByLabel("rate limit").fill(String(data.rateLimitRps));

    // Wait for the API key notice — this is the only time the plaintext key appears
    const [notice] = await Promise.all([
      this.page.waitForSelector(".alert-success, .notice:has-text('API key')", { timeout: 10_000 }),
      this.page.getByRole("button", { name: /save|create/i }).click(),
    ]);

    const noticeText = await notice.textContent();

    // Extract the API key from the notice: "Agent created. API key (shown once): <key>"
    const keyMatch = noticeText?.match(/API key \(shown once\):\s*([A-Za-z0-9_-]+)/);
    const apiKey = keyMatch?.[1] ?? "";

    // Extract agent ID from the URL or from the redirect
    const agentId = await this.getAgentIdFromUrl();

    return { agentId, apiKey };
  }

  private async getAgentIdFromUrl(): Promise<string> {
    const url = this.page.url();
    // URL might be /admin/resources/agents/agent_xxx/show or redirected to list
    const match = url.match(/\/agents\/([^\/]+)/);
    if (match) return match[1];

    // Fallback: get the last row's ID from the list
    const firstRow = this.page.locator("tr").first();
    const idCell = firstRow.locator("td").first();
    return (await idCell.textContent())?.trim() ?? "";
  }

  // ── Revoke agent ───────────────────────────────────────
  async revokeAgent(agentId: string) {
    const row = this.page.locator("tr").filter({ has: this.page.locator(`[data-id="${agentId}"]`) });
    // If data-id is not available, filter by text
    const revocableRow = this.getRowByName(new RegExp(agentId));
    const revokeBtn = revocableRow.getByRole("button", { name: /revoke/i });
    await revokeBtn.click();
  }

  // ── Show agent detail ──────────────────────────────────
  async gotoShow(agentId: string) {
    await this.goto(`/admin/resources/agents/${agentId}/show`);
  }
}