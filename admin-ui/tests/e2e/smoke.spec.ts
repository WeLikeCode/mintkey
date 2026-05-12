/**
 * Headless-browser smoke test for the admin-UI bug fixes (commit 465e445).
 *
 * Verifies, end to end, in a real Chromium:
 *   1. login with the bootstrap operator works and lands on /admin
 *   2. /admin renders the *custom* dashboard (Quick-start checklist / onboarding
 *      empty state) — NOT the stock AdminJS "Welcome on Board!" tips screen
 *      (ADMIN_UI_SPEC.md §2.1; was Bug 2)
 *   3. every one of the 7 resource lists renders without a red "Javascript
 *      Error" box (was Bug 3 — `properties` reconciled with `*Properties`)
 *   4. the tenants `new` form renders and submits without the
 *      `TypeError: ... record.errors is undefined` crash (was Bug 1 — the
 *      `recordJSON()` helper now returns a real RecordJSON with `errors: {}`)
 *
 * Run: MINTKEY_ADMIN_PASSWORD="$(cat ../data/bootstrap-secrets/admin_password)" \
 *        npx playwright test tests/e2e/smoke.spec.ts
 * (config: admin-ui/playwright.config.ts — testDir ./tests/e2e, baseURL :8081)
 *
 * Source: team/remediation/ADMIN_UI_SPEC.md §2.1, §4; ADR-0019.
 */

import { test, expect, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const ADMIN_EMAIL = process.env.MINTKEY_ADMIN_USER ?? "admin@mintkey.internal";
const ADMIN_PASSWORD = process.env.MINTKEY_ADMIN_PASSWORD ?? "";

const SCREENSHOT_DIR = path.resolve(process.cwd(), "test-results", "smoke-screenshots");
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const RESOURCE_LISTS = [
  "services",
  "agents",
  "permission_grants",
  "service_api_keys",
  "credentials",
  "audit_events",
  "tenants",
] as const;

// Strings that, if visible on the page, indicate the AdminJS frontend threw
// (the very class of failure the 465e445 fixes were about).
const JS_ERROR_NEEDLES = [
  "Javascript Error",
  "JavaScript Error",
  "record.errors is undefined",
  "Cannot read properties of undefined (reading 'errors')",
  "Cannot read property 'errors' of undefined",
  "TypeError: Cannot read",
  "Application error",
];

async function bodyText(page: Page): Promise<string> {
  return (await page.locator("body").innerText().catch(() => "")) ?? "";
}

async function expectNoJsErrorBox(page: Page, where: string): Promise<void> {
  const body = await bodyText(page);
  for (const needle of JS_ERROR_NEEDLES) {
    expect(body, `${where}: page shows "${needle}" — AdminJS frontend threw`).not.toContain(needle);
  }
}

async function login(page: Page): Promise<void> {
  await page.goto("/admin/login", { waitUntil: "domcontentloaded" });
  // AdminJS renders the login form via React bundles.
  await page.waitForSelector("input[type=email], input[name=email]", { timeout: 25_000 });
  await page.locator("input[type=email], input[name=email]").first().fill(ADMIN_EMAIL);
  await page.locator("input[type=password], input[name=password]").first().fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: /sign in|log\s?in/i }).first().click();
  // Be tolerant of the exact post-login route; just make sure we leave /login.
  await page.waitForFunction(() => !window.location.pathname.includes("/login"), undefined, {
    timeout: 25_000,
  });
}

test.describe("admin-ui smoke (465e445 fixes)", () => {
  test.beforeAll(() => {
    expect(
      ADMIN_PASSWORD,
      "MINTKEY_ADMIN_PASSWORD env var is required — set it from data/bootstrap-secrets/admin_password",
    ).not.toEqual("");
  });

  test("login → custom dashboard → 7 resource lists → tenants new-form", async ({ page }) => {
    // ---- 1 + 2: login, land on the custom dashboard ----
    await login(page);
    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    // The custom dashboard renders this H2 once it has fetched /admin/api/dashboard.
    await page
      .getByText(/Mintkey — credential broker for AI agents/i)
      .first()
      .waitFor({ timeout: 25_000 });

    const dashText = await bodyText(page);
    // The custom dashboard shows the Quick-start checklist OR (when nothing
    // exists yet) the onboarding empty state — both are part of ADMIN_UI_SPEC §2.1.
    expect(
      /Quick start|Register (a|your first) backend service/i.test(dashText),
      "dashboard should show the custom Quick-start checklist or onboarding empty state",
    ).toBe(true);
    // It must NOT be the stock AdminJS landing.
    expect(dashText, "dashboard must not be the stock AdminJS 'Welcome on Board' screen").not.toMatch(
      /Welcome on Board/i,
    );
    await expectNoJsErrorBox(page, "dashboard");
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "01-dashboard.png"), fullPage: true });

    // ---- 3: each of the 7 resource lists renders without a JS-error box ----
    for (const res of RESOURCE_LISTS) {
      await page.goto(`/admin/resources/${res}`, { waitUntil: "domcontentloaded" });
      // A list view renders either a <table> (with data) or a "No records"
      // placeholder (when empty) — both are a *successful* render. The old Bug-3
      // failure mode would show "Javascript Error" instead.
      await page
        .locator('table, :text("No records")')
        .first()
        .waitFor({ state: "visible", timeout: 25_000 })
        .catch(() => {
          /* fall through to the error-box assertion + screenshot below */
        });
      await expectNoJsErrorBox(page, `resource list /${res}`);
      // Belt and braces: confirm SOMETHING list-like rendered.
      const hasTable = (await page.locator("table").count()) > 0;
      const hasNoRecords = /No records/i.test(await bodyText(page));
      expect(hasTable || hasNoRecords, `resource list /${res}: neither a table nor a "No records" placeholder rendered`).toBe(true);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `02-list-${res}.png`), fullPage: true });
    }

    // ---- 4: tenants `new` form — must not crash with the record.errors TypeError ----
    await page.goto("/admin/resources/tenants/actions/new", { waitUntil: "domcontentloaded" });
    // The new-form should render a <form> with inputs. If the old bug were
    // present the page would show a "Javascript Error" / "record.errors is
    // undefined" box instead of the form.
    await page.locator("form").first().waitFor({ state: "visible", timeout: 25_000 }).catch(() => {});
    await expectNoJsErrorBox(page, "tenants new-form (initial render)");
    // At least one editable field must be present (the form actually rendered).
    const fieldCount = await page.locator("form input, form select, form textarea").count();
    expect(fieldCount, "tenants new-form rendered no fields — it likely crashed").toBeGreaterThan(0);

    // Fill the fields the Tenants resource exposes (slug, display name, isolation mode).
    // Selectors are defensive: match by name, fall back gracefully.
    const slugInput = page.locator('input[name="slug"], input[name="tenant_slug"]').first();
    if (await slugInput.count()) {
      await slugInput.fill("t_smoke");
    }
    const displayNameInput = page
      .locator('input[name="display_name"], input[name="displayName"], input[name="name"]')
      .first();
    if (await displayNameInput.count()) {
      await displayNameInput.fill("Smoke Tenant");
    }
    // isolation mode is a <select> per ADMIN_UI_SPEC §2.9 (value `row`).
    const isolationSelect = page
      .locator('select[name="isolation_mode"], select[name="isolationMode"]')
      .first();
    if (await isolationSelect.count()) {
      const opts = await isolationSelect.locator("option").allTextContents();
      const rowOpt = opts.find((o) => /row/i.test(o));
      await isolationSelect
        .selectOption(rowOpt ? { label: rowOpt } : { index: Math.max(0, opts.length - 1) })
        .catch(() => {});
    }

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "03-tenants-new-filled.png"), fullPage: true });

    // Submit. AdminJS "Save" button is typically labelled "Save".
    const saveBtn = page.getByRole("button", { name: /^save$/i }).first();
    if (await saveBtn.count()) {
      await saveBtn.click().catch(() => {});
      // Give the request time to complete and the result to render.
      await page.waitForTimeout(3000);
    }
    // The acceptance bar: the submit result is a success notice OR a normal
    // validation message — NOT a TypeError / JS-error box.
    await expectNoJsErrorBox(page, "tenants new-form (after submit)");
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "04-tenants-new-result.png"), fullPage: true });
  });
});
