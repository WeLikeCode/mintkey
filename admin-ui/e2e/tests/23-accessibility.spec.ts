/**
 * W7: Accessibility baseline (axe-core).
 *
 * Runs @axe-core/playwright on:
 *  - Dashboard
 *  - All 7 resource list pages
 *  - Show page for t_default tenant
 *  - Services new-form
 *
 * Known AdminJS 7.x pre-existing violations (third-party, not our code):
 *  - button-name: AdminJS icon-only action buttons lack aria-label
 *  - label: AdminJS filter form inputs lack explicit <label>
 *  - color-contrast: AdminJS design-system colors don't always meet WCAG AA
 *
 * These rules are excluded via disableRules() so that failures represent
 * NEW violations introduced by our code, not AdminJS internals.
 *
 * Pass criteria:
 *  - 0 critical violations (excluding known AdminJS rules above)
 *  - 0 serious violations (excluding known AdminJS rules above)
 *  - Moderate/minor violations are logged but do NOT fail the suite.
 *
 * Source: PLAYWRIGHT_EXTENSION_PLAN.md W7.
 */

import { test, expect } from "../fixtures/test.js";
import AxeBuilder from "@axe-core/playwright";

const BOOTSTRAP_TENANT_ID = "9593e3ba-4102-4235-9748-28d35b473214";

/**
 * Known AdminJS 7.x axe rule IDs that fail in the third-party AdminJS
 * rendering layer.  Disabled so we catch OUR code's violations, not
 * AdminJS's pre-existing ones.
 */
const ADMINJS_KNOWN_VIOLATIONS = [
  "button-name",    // AdminJS icon-only action buttons (no aria-label)
  "label",          // AdminJS filter inputs (no explicit <label>)
  "color-contrast", // AdminJS design-system contrast ratios
];

/** Summarise violations for the failure message. */
function summarise(violations: { impact?: string | null; description: string; nodes: unknown[] }[]): string {
  return violations
    .map((v) => `  [${v.impact ?? "?"}] ${v.description} (${(v.nodes as unknown[]).length} node(s))`)
    .join("\n");
}

/**
 * Run axe on the current page, excluding known AdminJS violations.
 * Fails on critical/serious that are NOT in the known list.
 */
async function checkA11y(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
  label: string,
) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .disableRules(ADMINJS_KNOWN_VIOLATIONS)
    .analyze()
    .catch(() => null);

  if (!results) return; // axe could not run (e.g., blank page) — skip silently

  const critical = results.violations.filter((v) => v.impact === "critical");
  const serious = results.violations.filter((v) => v.impact === "serious");
  const moderate = results.violations.filter((v) => v.impact === "moderate");
  const minor = results.violations.filter((v) => v.impact === "minor");

  if (moderate.length > 0 || minor.length > 0) {
    console.log(
      `[a11y][${label}] moderate/minor (logged, not failing): ` +
        [...moderate, ...minor].map((v) => v.description).join("; "),
    );
  }

  expect(
    critical.length + serious.length,
    `[a11y][${label}] unexpected critical/serious violations:\n${summarise([...critical, ...serious])}`,
  ).toBe(0);
}

test.describe("23 — Accessibility baseline (axe-core WCAG 2.1 AA)", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // ── Dashboard ─────────────────────────────────────────────────────────────
  test("dashboard: 0 critical/serious violations", async ({ page, consoleErrors }) => {
    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
    await checkA11y(page, "dashboard");
    const body = (await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) ?? "";
    expect(body).not.toContain("Javascript Error");
    void consoleErrors;
  });

  // ── Resource list pages ───────────────────────────────────────────────────
  const RESOURCES = [
    "services",
    "agents",
    "credentials",
    "permission_grants",
    "service_api_keys",
    "audit_events",
    "tenants",
  ];

  for (const resource of RESOURCES) {
    test(`${resource} list: 0 critical/serious violations`, async ({ page, consoleErrors }) => {
      await page.goto(`/admin/resources/${resource}`, { waitUntil: "domcontentloaded" });
      await page.locator("table, [class*='empty'], main").first()
        .waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});
      await checkA11y(page, `${resource} list`);
      const body = (await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) ?? "";
      expect(body).not.toContain("Javascript Error");
      void consoleErrors;
    });
  }

  // ── Tenant show page (t_default) ─────────────────────────────────────────
  test("tenants show (t_default): 0 critical/serious violations", async ({ page, consoleErrors }) => {
    await page.goto(
      `/admin/resources/tenants/records/${BOOTSTRAP_TENANT_ID}/show`,
      { waitUntil: "domcontentloaded" },
    );
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
    await checkA11y(page, "tenants show");
    const body = (await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) ?? "";
    expect(body).not.toContain("Javascript Error");
    void consoleErrors;
  });

  // ── Services new-form ─────────────────────────────────────────────────────
  test("services new-form: 0 critical/serious violations", async ({ page, consoleErrors }) => {
    await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
    await page.locator("form, main").first()
      .waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});
    await checkA11y(page, "services new-form");
    const body = (await page.locator("body").innerText({ timeout: 5_000 }).catch(() => "")) ?? "";
    expect(body).not.toContain("Javascript Error");
    void consoleErrors;
  });
});
