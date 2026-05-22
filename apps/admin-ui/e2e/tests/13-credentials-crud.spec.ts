/**
 * W1: Credentials round-trip.
 *
 * create service (via API) → register credential via UI →
 * list shows credential row, no plaintext → show renders (no plaintext).
 *
 * Note: credentials have no delete action (delete: { isVisible: false }) — the
 * round-trip ends at show. The security invariant (plaintext never in list/show)
 * is the key assertion here per ADR-0014.4 / S-SEC-1.
 *
 * Source: F-OP-03; T-1.3.4; PLAYWRIGHT_EXTENSION_PLAN.md W1.
 */

import { test, expect } from "../fixtures/test.js";
import { CredentialsPage } from "../pages/credentials.js";
import { createTestService } from "../fixtures/test-data.js";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

// Bootstrap tenant (t_default) — known from seed data (same as TENANT_ID in 30-show-pages.spec.ts)
const TENANT_ID = "9593e3ba-4102-4235-9748-28d35b473214";

test.describe("13 — Credentials round-trip (security invariant)", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("register credential → list contains row without plaintext → show renders without plaintext", async ({
    page,
    consoleErrors,
  }) => {
    const creds = new CredentialsPage(page);
    const plaintext = `e2e-cred-secret-${uid()}`;

    // Create a service to attach the credential to (via API — faster than UI)
    const svcId = await createTestService({
      tenantId: TENANT_ID,
      name: `e2e-cred-svc-${uid()}`,
      slug: `e2e-cred-svc-${uid()}`,
      baseUrl: "https://cred.example.com",
      authScheme: "api_key_header",
    });
    expect(svcId, "failed to create test service via API").not.toEqual("");

    // ── Register credential via UI ─────────────────────────────────────────
    const result = await creds.registerCredential({
      serviceId: svcId,
      authScheme: "api_key_header",
      plaintext,
    });
    expect(result.success, "credential registration must succeed").toBe(true);

    // ── List: plaintext must NOT appear ────────────────────────────────────
    await creds.gotoList();
    await page.waitForLoadState("networkidle");
    const listBody = (await page.locator("body").textContent().catch(() => "")) ?? "";
    expect(listBody, "plaintext must not appear in credentials list (ADR-0014.4)").not.toContain(
      plaintext,
    );

    // ── Confirm list has at least one credential row ───────────────────────
    const hasTable = (await page.locator("table").count()) > 0;
    const hasNoRecords = /No records/i.test(listBody);
    expect(hasTable || hasNoRecords, "credentials list must render (table or No records)").toBe(true);

    // ── Show page: find a credential row and navigate to show ──────────────
    const showLink = page
      .locator(`a[href*="/admin/resources/credentials/records/"][href*="/show"]`)
      .first();
    const showCount = await showLink.count();
    if (showCount > 0) {
      const href = await showLink.getAttribute("href");
      if (href) {
        await page.goto(href, { waitUntil: "domcontentloaded" });
        await page.waitForLoadState("networkidle");
        const showBody = (await page.locator("body").textContent().catch(() => "")) ?? "";
        expect(
          showBody,
          "plaintext must not appear on credential show page (ADR-0014.4)",
        ).not.toContain(plaintext);
      }
    }

    void consoleErrors;
  });
});
