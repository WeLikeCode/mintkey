/**
 * W0 migration: smoke regression — 7 resource lists + tenants new-form.
 *
 * Migrated from admin-ui/tests/e2e/smoke.spec.ts.
 * Verifies AdminJS renders each resource list without a "Javascript Error" box
 * and that the tenants new-form does not throw the record.errors TypeError.
 *
 * Source: team/remediation/ADMIN_UI_SPEC.md §2.1, §4; ADR-0019.
 */

import * as path from "path";
import { test, expect } from "../fixtures/test.js";

const RESOURCE_LISTS = [
  "services",
  "agents",
  "permission_grants",
  "service_api_keys",
  "credentials",
  "audit_events",
  "tenants",
] as const;

const JS_ERROR_NEEDLES = [
  "Javascript Error",
  "JavaScript Error",
  "record.errors is undefined",
  "Cannot read properties of undefined (reading 'errors')",
  "Cannot read property 'errors' of undefined",
  "TypeError: Cannot read",
  "Application error",
];

async function bodyText(page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never): Promise<string> {
  return (await page.locator("body").innerText().catch(() => "")) ?? "";
}

test.describe("26 — Smoke regression: 7 resource lists + tenants new-form", () => {
  test.beforeAll(() => {
    expect(
      process.env.PLAYWRIGHT_PASS ?? "",
      "PLAYWRIGHT_PASS env var is required",
    ).not.toEqual("");
  });

  test("dashboard: custom Quick-start renders, no JS errors", async ({ page, consoleErrors }) => {
    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page
      .getByText(/Mintkey — credential broker for AI agents/i)
      .first()
      .waitFor({ timeout: 25_000 });

    const body = await bodyText(page);
    expect(
      /Quick start|Register (a|your first) backend service/i.test(body),
      "dashboard should show the custom Quick-start checklist or onboarding empty state",
    ).toBe(true);
    expect(body, "dashboard must not show stock AdminJS 'Welcome on Board' screen").not.toMatch(
      /Welcome on Board/i,
    );
    for (const needle of JS_ERROR_NEEDLES) {
      expect(body, `dashboard: "${needle}" found`).not.toContain(needle);
    }
    void consoleErrors; // fixture auto-checks after test
  });

  for (const res of RESOURCE_LISTS) {
    test(`resource list /${res} renders without JS-error box`, async ({ page, consoleErrors }) => {
      await page.goto(`/admin/resources/${res}`, { waitUntil: "domcontentloaded" });
      await page
        .locator('table, :text("No records")')
        .first()
        .waitFor({ state: "visible", timeout: 25_000 })
        .catch(() => {});

      const body = await bodyText(page);
      for (const needle of JS_ERROR_NEEDLES) {
        expect(body, `/${res}: "${needle}" found`).not.toContain(needle);
      }
      const hasTable = (await page.locator("table").count()) > 0;
      const hasNoRecords = /No records/i.test(body);
      expect(hasTable || hasNoRecords, `/${res}: neither table nor "No records" rendered`).toBe(true);
      void consoleErrors;
    });
  }

  test("tenants new-form renders without record.errors TypeError", async ({ page, consoleErrors }) => {
    await page.goto("/admin/resources/tenants/actions/new", { waitUntil: "domcontentloaded" });
    await page.locator("form").first().waitFor({ state: "visible", timeout: 25_000 }).catch(() => {});

    const body = await bodyText(page);
    for (const needle of JS_ERROR_NEEDLES) {
      expect(body, `tenants new-form: "${needle}" found`).not.toContain(needle);
    }
    const fieldCount = await page.locator("form input, form select, form textarea").count();
    expect(fieldCount, "tenants new-form rendered no fields — it likely crashed").toBeGreaterThan(0);
    void consoleErrors;
  });
});
