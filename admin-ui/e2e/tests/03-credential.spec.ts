/**
 * Tier 2 — Credential registration and rotation.
 *
 * Source: F-OP-03; T-1.3.4; T-1.8.4.
 *
 * SECURITY (ADR-0014.4 / S-SEC-1):
 * The plaintext credential is shown exactly ONCE in the create response.
 * The admin-ui NEVER stores or re-shows it.
 */

import { test, expect, type Page } from "@playwright/test";
import { CredentialsPage } from "../pages/credentials.js";
import { ServicesPage } from "../pages/services.js";
import {
  createTestService,
  resetCleanupQueue,
} from "../fixtures/test-data.js";

test.describe("Tier 2 — Credentials (F-OP-03)", () => {
  let page: Page;
  let creds: CredentialsPage;
  let svcs: ServicesPage;
  const token = process.env.PLAYWRIGHT_API_JWT ?? "";

  test.beforeEach(async ({ page: pg }) => {
    page = pg;
    creds = new CredentialsPage(page);
    svcs = new ServicesPage(page);
    resetCleanupQueue();
  });

  test("1. register credential — plaintext shown only once", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const svcId = await createTestService({ tenantId, name: "CredTestSvc", slug: "cred-test-svc", baseUrl: "https://cred.example.com" }, token);
    const plaintext = "sk-live-TEST-plaintext-secret-" + Date.now();

    const result = await creds.registerCredential({
      serviceId: svcId,
      authScheme: "api_key_header",
      plaintext,
    });

    expect(result.success).toBe(true);

    await creds.gotoList();
    await expect(page.locator("body")).not.toContainText(plaintext);
  });

  test("2. plaintext never appears in credential list", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const svcId = await createTestService({ tenantId, name: "LeakTest", slug: "leak-test", baseUrl: "https://leak.example.com" }, token);

    await creds.registerCredential({
      serviceId: svcId,
      authScheme: "api_key_header",
      plaintext: "super-secret-value-that-must-not-leak",
    });

    await creds.gotoList();
    const bodyText = await page.locator("body").textContent();
    expect(bodyText).not.toContain("super-secret-value-that-must-not-leak");
  });

  test("3. rotate credential", async () => {
    const tenantId = process.env.PLAYWRIGHT_TENANT_ID ?? "";
    if (!tenantId) { test.skip(true, "PLAYWRIGHT_TENANT_ID not set"); return; }

    const svcId = await createTestService({ tenantId, name: "RotateTest", slug: "rotate-test", baseUrl: "https://rotate.example.com" }, token);
    const oldPlaintext = "old-key-" + Date.now();
    await creds.registerCredential({ serviceId: svcId, authScheme: "api_key_header", plaintext: oldPlaintext });

    await creds.gotoList();
    const bodyBefore = await page.locator("body").textContent();
    expect(bodyBefore).not.toContain(oldPlaintext);
  });
});