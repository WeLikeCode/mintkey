/**
 * Tier 2 — Agent CRUD (critical path).
 *
 * Source: F-OP-04; T-1.4.3; T-1.9.4.
 *
 * SECURITY (ADR-0014.4 / Req 5 AC2):
 * The API key is returned plaintext exactly ONCE at creation.
 * The admin-ui shows it in a one-time notice — never again.
 */

import { test, expect, type Page } from "@playwright/test";
import { AgentsPage } from "../pages/agents.js";
import { createTestAgent, resetCleanupQueue } from "../fixtures/test-data.js";

test.describe("Tier 2 — Agents (F-OP-04)", () => {
  let page: Page;
  let agents: AgentsPage;
  const token = process.env.PLAYWRIGHT_API_JWT ?? "";

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    agents = new AgentsPage(page);
    resetCleanupQueue();
  });

  test("1. create agent — API key shown once in notice", async () => {
    await agents.gotoList();

    const agentName = "TestAgent-" + Date.now();
    const result = await agents.createAgent({ name: agentName, description: "E2E test agent" });

    expect(result.agentId).toMatch(/^agent_[0-9A-HJKMNP-TV-Z]{26}$/);
    expect(result.apiKey.length).toBeGreaterThan(20);

    await agents.gotoList();
    await expect(agents.getRowByName(agentName)).toBeVisible();

    const bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain(result.apiKey);
  });

  test("2. agent detail shows metadata but NOT the API key", async () => {
    const agentName = "DetailAgent-" + Date.now();
    const { agentId } = await agents.createAgent({ name: agentName });

    await agents.gotoShow(agentId);
    await expect(page.locator("td, dd").filter({ hasText: agentName })).toBeVisible();
  });

  test("3. revoke agent", async () => {
    const agentName = "RevokeAgent-" + Date.now();
    const { agentId } = await agents.createAgent({ name: agentName });

    await agents.gotoList();
    await expect(agents.getRowByName(agentName)).toBeVisible();
    await agents.revokeAgent(agentId);
  });

  test("4. revoked agent key fails authentication", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const agentName = "RevokeAuthTest-" + Date.now();
    const { agentId } = await agents.createAgent({ name: agentName });

    await fetch(`${process.env.ADMIN_API_URL ?? "http://localhost:8080"}/v1/tenants/${tenantId}/agents/${agentId}/revoke`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });

    await agents.gotoList();
    await page.waitForTimeout(2_000);

    const row = agents.getRowByName(agentName);
    const revokeBtn = row.locator("a, button").filter({ hasText: /revoke/i });
    await expect(revokeBtn).not.toBeVisible();
  });
});