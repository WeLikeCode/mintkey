/**
 * Tier 1 — Permission grants.
 *
 * Source: F-OP-04; T-1.4.3.
 */

import { test, expect, type Page } from "@playwright/test";
import { PermissionsPage } from "../pages/permissions.js";
import { AgentsPage } from "../pages/agents.js";
import {
  createTestAgent,
  createTestService,
  createTestPermission,
  resetCleanupQueue,
} from "../fixtures/test-data.js";

test.describe("Tier 1 — Permissions (F-OP-04)", () => {
  let page: Page;
  let perms: PermissionsPage;
  let agents: AgentsPage;
  const token = process.env.PLAYWRIGHT_API_JWT ?? "";

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    perms = new PermissionsPage(page);
    agents = new AgentsPage(page);
    resetCleanupQueue();
  });

  test("1. grant permission to agent", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const svcId = await createTestService({ tenantId, name: "PermSvc", slug: "perm-svc" }, token);
    const { agentId } = await agents.createAgent({ name: "PermAgent" });

    await perms.grantPermission({
      agent_id: agentId,
      service_id: svcId,
      action: "read:health",
    });

    await expect(page.locator('[data-testid="notice-wrapper"]')).toBeVisible();
  });

  test("2. grant then revoke permission", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const svcId = await createTestService({ tenantId, name: "RevokePermSvc", slug: "revoke-perm-svc" }, token);
    const { agentId } = await agents.createAgent({ name: "RevokePermAgent" });

    await perms.grantPermission({
      agent_id: agentId,
      service_id: svcId,
      action: "read:echo",
    });

    const permId = await createTestPermission({ tenantId, agentId, serviceId: svcId, action: "read:echo" }, token);
    await perms.revokePermission(permId);
  });
});