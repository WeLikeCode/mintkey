/**
 * W0 migration: show pages — no React #31 JS errors.
 *
 * Migrated from admin-ui/tests/e2e/show-pages.spec.ts.
 * Verifies that Show pages for all 7 resources do not display a
 * "Javascript Error" box and render JSON columns as readable text.
 *
 * Root cause fixed: JSON columns declared type:"string" caused React
 * invariant #31. Fix: type:"mixed" + custom JsonValue.tsx component.
 *
 * Source: fix-show-page-react-31 chunk; ADR-0019.
 */

import { test, expect } from "../fixtures/test.js";

// Known record IDs from the bootstrap seed
const TENANT_ID = "9593e3ba-4102-4235-9748-28d35b473214";

const JS_ERROR_NEEDLES = [
  "Javascript Error",
  "JavaScript Error",
  "Minified React error",
  "object with keys",
  "Objects are not valid as a React child",
  "TypeError",
  "Application error",
];

async function expectNoJsError(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
  where: string,
): Promise<string> {
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
  const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
  for (const needle of JS_ERROR_NEEDLES) {
    expect(body, `${where}: "${needle}" found`).not.toContain(needle);
  }
  return body;
}

async function firstRecordId(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
  resource: string,
): Promise<string | null> {
  await page.goto(`/admin/resources/${resource}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
  const showLink = page
    .locator(`a[href*="/admin/resources/${resource}/records/"][href*="/show"]`)
    .first();
  if ((await showLink.count()) === 0) return null;
  const href = await showLink.getAttribute("href");
  if (!href) return null;
  const m = href.match(/\/records\/([^/]+)\/show/);
  return m ? m[1] : null;
}

test.describe("30 — Show pages: no React #31 JS errors", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS env var is required").not.toEqual("");
  });

  test("Tenants Show (t_default): no JS error, settings renders", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto(`/admin/resources/tenants/records/${TENANT_ID}/show`, {
      waitUntil: "domcontentloaded",
    });
    const body = await expectNoJsError(page, "tenants show");
    expect(body, "Tenants Show: 'Default Tenant' or 't_default' should appear").toMatch(
      /Default Tenant|t_default/i,
    );
    expect(body, "Tenants Show: 'isolation_mode' label or placeholder should be visible").toMatch(
      /isolation_mode|—/i,
    );
    void consoleErrors;
  });

  test("Services Show: no JS error", async ({ page, consoleErrors }) => {
    const recordId = await firstRecordId(page, "services");
    if (!recordId) {
      await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
      await expectNoJsError(page, "services list (no records to show)");
      return;
    }
    await page.goto(`/admin/resources/services/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    await expectNoJsError(page, "services show");
    void consoleErrors;
  });

  test("Agents Show: no JS error", async ({ page, consoleErrors }) => {
    const recordId = await firstRecordId(page, "agents");
    if (!recordId) {
      await page.goto("/admin/resources/agents", { waitUntil: "domcontentloaded" });
      await expectNoJsError(page, "agents list (no records to show)");
      return;
    }
    await page.goto(`/admin/resources/agents/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    await expectNoJsError(page, "agents show");
    void consoleErrors;
  });

  test("Permission Grants Show: no JS error, constraints renders", async ({
    page,
    consoleErrors,
  }) => {
    const recordId = await firstRecordId(page, "permission_grants");
    if (!recordId) {
      await page.goto("/admin/resources/permission_grants", { waitUntil: "domcontentloaded" });
      await expectNoJsError(page, "permission_grants list (no records to show)");
      return;
    }
    await page.goto(`/admin/resources/permission_grants/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    const body = await expectNoJsError(page, "permission_grants show");
    expect(body, "Permissions Show: 'Constraints' label should be visible").toMatch(/Constraints/i);
    void consoleErrors;
  });

  test("Service API Keys Show: no JS error, constraints renders", async ({
    page,
    consoleErrors,
  }) => {
    const recordId = await firstRecordId(page, "service_api_keys");
    if (!recordId) {
      await page.goto("/admin/resources/service_api_keys", { waitUntil: "domcontentloaded" });
      await expectNoJsError(page, "service_api_keys list (no records to show)");
      return;
    }
    await page.goto(`/admin/resources/service_api_keys/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    const body = await expectNoJsError(page, "service_api_keys show");
    expect(body, "API Keys Show: 'Constraints' label should be visible").toMatch(/Constraints/i);
    void consoleErrors;
  });

  test("Credentials Show: no JS error", async ({ page, consoleErrors }) => {
    const recordId = await firstRecordId(page, "credentials");
    if (!recordId) {
      await page.goto("/admin/resources/credentials", { waitUntil: "domcontentloaded" });
      await expectNoJsError(page, "credentials list (no records to show)");
      return;
    }
    await page.goto(`/admin/resources/credentials/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    await expectNoJsError(page, "credentials show");
    void consoleErrors;
  });

  test("Audit Events Show: no JS error, payload renders", async ({ page, consoleErrors }) => {
    const recordId = await firstRecordId(page, "audit_events");
    if (!recordId) {
      await page.goto("/admin/resources/audit_events", { waitUntil: "domcontentloaded" });
      await expectNoJsError(page, "audit_events list (no records)");
      return;
    }
    await page.goto(`/admin/resources/audit_events/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    const body = await expectNoJsError(page, "audit_events show");
    expect(body, "Audit Events Show: 'Payload' label should be visible").toMatch(/Payload/i);
    void consoleErrors;
  });
});
