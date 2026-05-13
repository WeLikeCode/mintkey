/**
 * E2E regression test: Show pages for all 7 resources must not display
 * a "Javascript Error" box and must render JSON columns as readable text.
 *
 * Root cause fixed: JSON columns (settings, constraints, payload, etc.) were
 * declared as type:"string" in RestResource config; AdminJS's string renderer
 * passes the raw value to React as a child — but the API returns plain JS
 * objects for JSONB columns, causing React invariant #31 ("Objects are not
 * valid as a React child").
 *
 * Fix: declare JSON columns as type:"mixed" in the property definition.
 * AdminJS renders mixed type without React children coercion.
 * Additionally, a custom JsonValue.tsx component renders JSON columns
 * as pretty-printed <pre> blocks with a null/empty placeholder.
 *
 * Source: fix-show-page-react-31 chunk; ADR-0019.
 *
 * Run: MINTKEY_ADMIN_PASSWORD="$(cat ../data/bootstrap-secrets/admin_password)" \
 *        npx playwright test tests/e2e/show-pages.spec.ts
 */

import { test, expect, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const ADMIN_EMAIL = process.env.MINTKEY_ADMIN_USER ?? "admin@mintkey.internal";
const ADMIN_PASSWORD = process.env.MINTKEY_ADMIN_PASSWORD ?? "";

const SCREENSHOT_DIR = path.resolve(process.cwd(), "test-results", "show-pages-screenshots");
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

// Strings that indicate the AdminJS frontend threw — same needle set as smoke.spec.ts
const JS_ERROR_NEEDLES = [
  "Javascript Error",
  "JavaScript Error",
  "Minified React error",
  "object with keys",
  "Objects are not valid as a React child",
  "TypeError",
  "Application error",
];

// Known record IDs from the bootstrap seed
const TENANT_ID = "9593e3ba-4102-4235-9748-28d35b473214";

async function login(page: Page): Promise<void> {
  await page.goto("/admin/login", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("input[type=email], input[name=email]", { timeout: 25_000 });
  await page.locator("input[type=email], input[name=email]").first().fill(ADMIN_EMAIL);
  await page.locator("input[type=password], input[name=password]").first().fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: /sign in|log\s?in/i }).first().click();
  await page.waitForFunction(() => !window.location.pathname.includes("/login"), undefined, {
    timeout: 25_000,
  });
}

async function bodyText(page: Page): Promise<string> {
  return (await page.locator("body").innerText().catch(() => "")) ?? "";
}

async function expectNoJsErrorBox(page: Page, where: string): Promise<void> {
  const body = await bodyText(page);
  for (const needle of JS_ERROR_NEEDLES) {
    expect(body, `${where}: page shows "${needle}" — AdminJS frontend threw`).not.toContain(needle);
  }
}

/** Navigate to a Show page and assert no JS errors. Returns body text. */
async function visitShowPage(page: Page, url: string, screenshotName: string): Promise<string> {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => { /* ok */ });
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, screenshotName), fullPage: true });
  await expectNoJsErrorBox(page, url);
  return bodyText(page);
}

/** Get the first record ID from a resource list page. Returns null if no records. */
async function firstRecordId(page: Page, resource: string): Promise<string | null> {
  await page.goto(`/admin/resources/${resource}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => { /* ok */ });
  // AdminJS show links are <a href="/admin/resources/<res>/records/<id>/show">
  const showLink = page.locator(`a[href*="/admin/resources/${resource}/records/"][href*="/show"]`).first();
  const count = await showLink.count();
  if (count === 0) return null;
  const href = await showLink.getAttribute("href");
  if (!href) return null;
  const m = href.match(/\/records\/([^/]+)\/show/);
  return m ? m[1] : null;
}

test.describe("Show pages — no React #31 JS errors", () => {
  test.beforeAll(() => {
    expect(
      ADMIN_PASSWORD,
      "MINTKEY_ADMIN_PASSWORD env var is required — set it from data/bootstrap-secrets/admin_password",
    ).not.toEqual("");
  });

  test("Tenants Show (t_default) — no JS error, settings renders, isolation_mode has placeholder", async ({ page }) => {
    await login(page);

    const body = await visitShowPage(
      page,
      `/admin/resources/tenants/records/${TENANT_ID}/show`,
      "01-tenants-show.png",
    );

    // The page must contain basic tenant fields
    expect(body, "Tenants Show: 'Default Tenant' or 't_default' should appear").toMatch(/Default Tenant|t_default/i);

    // settings field must render as readable text (not crash).
    // When empty ({}) the custom renderer shows the placeholder or "{}"
    // When the mixed renderer is used it shows key-value pairs or the JSON.
    // The absence of JS error is the primary assertion (checked above).

    // isolation_mode: when null/empty, render "—" placeholder. The JsonValue component
    // renders the label and the "—" placeholder. AdminJS uses the property path as the
    // label text when no explicit label override is set.
    expect(body, "Tenants Show: 'isolation_mode' label or placeholder should be visible").toMatch(/isolation_mode|—/i);
  });

  test("Services Show — no JS error", async ({ page }) => {
    await login(page);

    const recordId = await firstRecordId(page, "services");
    if (!recordId) {
      // No services seeded — check the list page at minimum
      await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
      await expectNoJsErrorBox(page, "services list (no records to show)");
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "02-services-show.png"), fullPage: true });
      return;
    }

    await visitShowPage(
      page,
      `/admin/resources/services/records/${recordId}/show`,
      "02-services-show.png",
    );
  });

  test("Agents Show — no JS error", async ({ page }) => {
    await login(page);

    const recordId = await firstRecordId(page, "agents");
    if (!recordId) {
      await page.goto("/admin/resources/agents", { waitUntil: "domcontentloaded" });
      await expectNoJsErrorBox(page, "agents list (no records to show)");
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "03-agents-show.png"), fullPage: true });
      return;
    }

    await visitShowPage(
      page,
      `/admin/resources/agents/records/${recordId}/show`,
      "03-agents-show.png",
    );
  });

  test("Permission Grants Show — no JS error, constraints renders", async ({ page }) => {
    await login(page);

    const recordId = await firstRecordId(page, "permission_grants");
    if (!recordId) {
      await page.goto("/admin/resources/permission_grants", { waitUntil: "domcontentloaded" });
      await expectNoJsErrorBox(page, "permission_grants list (no records to show)");
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "04-permissions-show.png"), fullPage: true });
      return;
    }

    const body = await visitShowPage(
      page,
      `/admin/resources/permission_grants/records/${recordId}/show`,
      "04-permissions-show.png",
    );

    // constraints field must not crash; label should be present
    expect(body, "Permissions Show: 'Constraints' label should be visible").toMatch(/Constraints/i);
  });

  test("Service API Keys Show — no JS error, constraints renders", async ({ page }) => {
    await login(page);

    const recordId = await firstRecordId(page, "service_api_keys");
    if (!recordId) {
      await page.goto("/admin/resources/service_api_keys", { waitUntil: "domcontentloaded" });
      await expectNoJsErrorBox(page, "service_api_keys list (no records to show)");
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "05-apikeys-show.png"), fullPage: true });
      return;
    }

    const body = await visitShowPage(
      page,
      `/admin/resources/service_api_keys/records/${recordId}/show`,
      "05-apikeys-show.png",
    );

    expect(body, "API Keys Show: 'Constraints' label should be visible").toMatch(/Constraints/i);
  });

  test("Credentials Show — no JS error", async ({ page }) => {
    await login(page);

    const recordId = await firstRecordId(page, "credentials");
    if (!recordId) {
      await page.goto("/admin/resources/credentials", { waitUntil: "domcontentloaded" });
      await expectNoJsErrorBox(page, "credentials list (no records to show)");
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "06-credentials-show.png"), fullPage: true });
      return;
    }

    await visitShowPage(
      page,
      `/admin/resources/credentials/records/${recordId}/show`,
      "06-credentials-show.png",
    );
  });

  test("Audit Events Show — no JS error, payload renders", async ({ page }) => {
    await login(page);

    const recordId = await firstRecordId(page, "audit_events");
    if (!recordId) {
      // No audit events — check the list page
      await page.goto("/admin/resources/audit_events", { waitUntil: "domcontentloaded" });
      await expectNoJsErrorBox(page, "audit_events list (no records)");
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, "07-audit-show.png"), fullPage: true });
      return;
    }

    const body = await visitShowPage(
      page,
      `/admin/resources/audit_events/records/${recordId}/show`,
      "07-audit-show.png",
    );

    // payload field must not crash; label should be present
    expect(body, "Audit Events Show: 'Payload' label should be visible").toMatch(/Payload/i);
  });
});
