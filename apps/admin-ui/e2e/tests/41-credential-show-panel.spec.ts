/**
 * 41 — OPS-Y: Credential show page enrichment panel.
 *
 * Asserts that the CredentialShowPanel renders correctly on the credential show
 * page, including:
 *   1. Intro paragraph with "envelope-encrypted in the Vault Adapter" text.
 *   2. "Service:" label with a hyperlink to the service show page.
 *   3. "View audit history" link with filters.target_id query param.
 *   4. "Last-used timestamp not yet tracked" backlog note.
 *   5. Clicking the Service link navigates to the services show page.
 *   6. Clicking the audit history link navigates to audit_events with the right filter.
 *
 * Source: OPS-Y spec; ADMIN_UI_SPEC.md §2.4; UX-CLARITY Pain 6.
 */

import { test, expect } from "../fixtures/test.js";

// webkit: AdminJS/Axios CORS — tracked W8
const skipWebkit = ({ browserName }: { browserName: string }) =>
  browserName === "webkit";

// ── helpers ──────────────────────────────────────────────────────────────────

/**
 * Navigate to credentials list, extract first record's show-page href,
 * then navigate there. Returns the record ID or null if no records.
 */
async function navigateToFirstCredentialShow(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
): Promise<string | null> {
  await page.goto("/admin/resources/credentials", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

  const showLink = page
    .locator('a[href*="/admin/resources/credentials/records/"][href*="/show"]')
    .first();

  if ((await showLink.count()) === 0) return null;
  const href = await showLink.getAttribute("href");
  if (!href) return null;

  await page.goto(href, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

  const m = href.match(/\/records\/([^/]+)\/show/);
  return m ? m[1] : null;
}

// ── Credential show panel ─────────────────────────────────────────────────────

test.describe("41 — OPS-Y: Credential show page enrichment panel", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("credential show page renders the intro panel with all four elements", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    const recordId = await navigateToFirstCredentialShow(page);
    if (!recordId) {
      test.skip(true, "No credentials found in the system — skip credential show panel test");
      return;
    }

    // 1. Intro paragraph with envelope-encrypted mention
    const introEl = page.locator('[data-testid="credential-show-panel-intro"]');
    await expect(introEl, "credential-show-panel-intro must be visible").toBeVisible({
      timeout: 15_000,
    });
    const introText = (await introEl.textContent()) ?? "";
    expect(
      introText,
      "intro must mention envelope-encrypted in the Vault Adapter",
    ).toContain("envelope-encrypted in the Vault Adapter");
    expect(introText, "intro must mention Egress Proxy").toContain("Egress Proxy");

    // 2. Service link
    const serviceLinkEl = page.locator('[data-testid="credential-show-panel-service-link"]');
    await expect(serviceLinkEl, "service link must be visible").toBeVisible({ timeout: 10_000 });
    const serviceHref = await serviceLinkEl.getAttribute("href");
    expect(serviceHref, "service link must point to the services show route").toMatch(
      /\/admin\/resources\/services\/records\/.+\/show/,
    );

    // 3. Audit history link
    const auditLinkEl = page.locator('[data-testid="credential-show-panel-audit-link"]');
    await expect(auditLinkEl, "audit history link must be visible").toBeVisible({ timeout: 10_000 });
    const auditHref = await auditLinkEl.getAttribute("href");
    expect(auditHref, "audit link must point to audit_events").toContain(
      "/admin/resources/audit_events",
    );
    expect(auditHref, "audit link must use filters.target_id query param").toContain(
      "filters.target_id=",
    );

    // 4. Backlog note
    const backlogEl = page.locator('[data-testid="credential-show-panel-backlog-note"]');
    await expect(backlogEl, "backlog note must be visible").toBeVisible({ timeout: 10_000 });
    const backlogText = (await backlogEl.textContent()) ?? "";
    expect(
      backlogText,
      "backlog note must mention 'Last-used timestamp not yet tracked'",
    ).toContain("Last-used timestamp not yet tracked");
    expect(backlogText, "backlog note must mention TODO-last-used").toContain("TODO-last-used");

    void consoleErrors;
  });

  test("clicking Service link on credential show page navigates to service show page", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    const recordId = await navigateToFirstCredentialShow(page);
    if (!recordId) {
      test.skip(true, "No credentials found — skip service link navigation test");
      return;
    }

    const serviceLinkEl = page.locator('[data-testid="credential-show-panel-service-link"]');
    await expect(serviceLinkEl, "service link must be visible before clicking").toBeVisible({
      timeout: 15_000,
    });

    // Click and wait for navigation
    await Promise.all([
      page.waitForURL(/\/admin\/resources\/services\/records\/.+\/show/, { timeout: 15_000 }),
      serviceLinkEl.click(),
    ]);

    // Confirm we landed on a services show page
    expect(page.url(), "URL must contain /admin/resources/services/records/").toMatch(
      /\/admin\/resources\/services\/records\/.+\/show/,
    );

    void consoleErrors;
  });

  test("clicking audit history link on credential show page navigates to audit_events with correct filter", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    const recordId = await navigateToFirstCredentialShow(page);
    if (!recordId) {
      test.skip(true, "No credentials found — skip audit link navigation test");
      return;
    }

    const auditLinkEl = page.locator('[data-testid="credential-show-panel-audit-link"]');
    await expect(auditLinkEl, "audit history link must be visible before clicking").toBeVisible({
      timeout: 15_000,
    });

    // Capture the href before clicking so we can verify filter param
    const auditHref = (await auditLinkEl.getAttribute("href")) ?? "";

    // Click and wait for navigation to the audit_events resource
    await Promise.all([
      page.waitForURL(/\/admin\/resources\/audit_events/, { timeout: 15_000 }),
      auditLinkEl.click(),
    ]);

    // Confirm URL contains audit_events and filters.target_id
    const finalUrl = page.url();
    expect(finalUrl, "URL must navigate to audit_events").toContain(
      "/admin/resources/audit_events",
    );
    expect(auditHref, "audit history link href must contain filters.target_id").toContain(
      "filters.target_id=",
    );

    void consoleErrors;
  });
});
