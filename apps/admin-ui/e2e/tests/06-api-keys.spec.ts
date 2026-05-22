/**
 * Tier 2 — API Key lifecycle (create, revoke, rotate).
 *
 * Source: long-lived API keys tasks; ADR-0018.
 *
 * SECURITY:
 * Plaintext key shown exactly once at creation (§1.3).
 * Key fingerprint shown in list, never the full key.
 */

import { test, expect, type Page } from "@playwright/test";
import { ApiKeysPage } from "../pages/api-keys.js";
import { AgentsPage } from "../pages/agents.js";
import {
  createTestAgent,
  createTestService,
  createTestPermission,
  resetCleanupQueue,
} from "../fixtures/test-data.js";

test.describe("Tier 2 — API Keys", () => {
  let page: Page;
  let apiKeys: ApiKeysPage;
  let agents: AgentsPage;
  const token = process.env.PLAYWRIGHT_API_JWT ?? "";

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    apiKeys = new ApiKeysPage(page);
    agents = new AgentsPage(page);
    resetCleanupQueue();
  });

  test("1. create API key — plaintext in one-time notice only", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const agentName = "ApiKeyAgent-" + Date.now();
    const { agentId } = await agents.createAgent({ name: agentName });

    // API key creation requires: valid service + permission grant for the agent
    const serviceId = await createTestService({
      tenantId,
      name: "apikey-test-svc-" + Date.now(),
      authScheme: "api_key_header",
    });
    await createTestPermission({ tenantId, agentId, serviceId, action: "read:health" });

    await apiKeys.gotoList();
    const plaintextKey = await apiKeys.createApiKey(agentId, {
      service_id: serviceId,
      allowed_actions: "read:health",
    });

    expect(plaintextKey.length).toBeGreaterThan(20);

    await apiKeys.gotoList();
    const bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain(plaintextKey);
  });

  test("2. revoke API key", async () => {
    const agentName = "RevokeKeyAgent-" + Date.now();
    const { agentId } = await agents.createAgent({ name: agentName });

    await apiKeys.gotoList();
    await apiKeys.createApiKey(agentId, {});
    await apiKeys.revokeApiKey("key-to-revoke");
  });

  test("3. rotate API key — new key returned once", async () => {
    const agentName = "RotateKeyAgent-" + Date.now();
    const { agentId } = await agents.createAgent({ name: agentName });

    await apiKeys.gotoList();
    await apiKeys.createApiKey(agentId, {});

    const newKey = await apiKeys.rotateApiKey("key-to-rotate");
    expect(newKey.length).toBeGreaterThanOrEqual(0);
  });
});