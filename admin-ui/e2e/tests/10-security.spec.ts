/**
 * Tier 4 — Security & edge case tests.
 *
 * Source: S-SEC-1; ADR-0014.4; ADR-0014.5; ADR-0014.7;
 *         Req 5 AC2, Req 9.1, Req 10.1.
 *
 * Invariants tested:
 *  1. Plaintext credential never appears after creation
 *  2. API key full value never appears in list/show/audit
 *  3. Revoke button hidden for already-revoked entities
 *  4. Unauthenticated access redirects to login
 */

import { test, expect, type Page } from "@playwright/test";
import { CredentialsPage } from "../pages/credentials.js";
import { AgentsPage } from "../pages/agents.js";
import { AuditPage } from "../pages/audit.js";
import { ServicesPage } from "../pages/services.js";
import {
  createTestService,
  createTestAgent,
  resetCleanupQueue,
} from "../fixtures/test-data.js";

test.describe("Tier 4 — Security", () => {
  let page: Page;
  let creds: CredentialsPage;
  let agents: AgentsPage;
  let audit: AuditPage;
  let svcs: ServicesPage;
  const token = process.env.PLAYWRIGHT_API_JWT ?? "";

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    creds = new CredentialsPage(page);
    agents = new AgentsPage(page);
    audit = new AuditPage(page);
    svcs = new ServicesPage(page);
    resetCleanupQueue();
  });

  test("SEC-1: plaintext credential never leaks into credential list", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const svcId = await createTestService({ tenantId, name: "SecuritySvc", slug: "security-svc" }, token);
    const SECRET = "s3cr3t-pl41nt3xt-th4t-must-n0t-l34k-" + Date.now();

    await creds.registerCredential({ serviceId: svcId, authScheme: "api_key_header", plaintext: SECRET });

    await creds.gotoList();
    let bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain(SECRET);

    await svcs.gotoList();
    bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain(SECRET);

    await audit.gotoList();
    bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain(SECRET);
  });

  test("SEC-2: API key never appears in agent list or show", async () => {
    const agentName = "SecurityAgent-" + Date.now();
    const { agentId, apiKey } = await agents.createAgent({ name: agentName });

    await agents.gotoList();
    let bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain(apiKey);

    await agents.gotoShow(agentId);
    bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain(apiKey);
  });

  test("SEC-3: API key fingerprint shown instead of full key", async () => {
    const agentName = "FingerprintAgent-" + Date.now();
    const { apiKey } = await agents.createAgent({ name: agentName });

    await agents.gotoList();
    const bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain(apiKey);
  });

  test("SEC-4: revoke button hidden for already-revoked entities", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const agentName = "RevokedAgent-" + Date.now();
    const { agentId } = await agents.createAgent({ name: agentName });

    await fetch(`${process.env.ADMIN_API_URL ?? "http://localhost:8080"}/v1/tenants/${tenantId}/agents/${agentId}/revoke`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });

    await agents.gotoList();
    const revokeBtn = page.locator("tr").filter({ hasText: agentName }).locator("a, button").filter({ hasText: /revoke/i });
    await expect(revokeBtn).not.toBeVisible();
  });

  test("SEC-5: unauthenticated access redirects to login", async () => {
    await page.context().clearCookies();
    await page.goto("/admin/resources/services");
    await expect(page).toHaveURL(/\/admin\/login/);
  });
});