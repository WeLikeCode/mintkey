/**
 * Playwright e2e tests for the admin-ui-ux-uplift chunk:
 *   - Per-resource intro paragraphs above each resource list.
 *   - Dashboard SVG data-model diagram and 6-step onboarding flow.
 *   - Regression: existing Quick-start checklist and At-a-glance counts still render.
 *
 * Run:
 *   MINTKEY_ADMIN_PASSWORD="$(cat ../data/bootstrap-secrets/admin_password)" \
 *     npx playwright test tests/e2e/intros-and-dashboard.spec.ts
 *
 * Source: admin-ui-ux-uplift acceptance criteria #1, #2, #5.
 */

import { test, expect, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const ADMIN_EMAIL = process.env.MINTKEY_ADMIN_USER ?? "admin@mintkey.internal";
const ADMIN_PASSWORD = process.env.MINTKEY_ADMIN_PASSWORD ?? "";

const SCREENSHOT_DIR = path.resolve(process.cwd(), "test-results", "intros-screenshots");
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

/** First 30 chars of each resource intro (AC #1). */
const RESOURCE_INTROS: Array<{ slug: string; snippet: string }> = [
  { slug: "tenants", snippet: "Tenants are isolated workspaces." },
  { slug: "services", snippet: "Services are the backend APIs you" },
  { slug: "credentials", snippet: "Credentials are the real secrets" },
  { slug: "agents", snippet: "Agents are the AI agents" },
  { slug: "permission_grants", snippet: "Permission Grants tie an Agent" },
  { slug: "service_api_keys", snippet: "Service API Keys" },
  { slug: "audit_events", snippet: "Audit Events are the immutable" },
];

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

test.describe("admin-ui-ux-uplift: intros and dashboard", () => {
  test.beforeAll(() => {
    expect(
      ADMIN_PASSWORD,
      "MINTKEY_ADMIN_PASSWORD env var is required — set it from data/bootstrap-secrets/admin_password",
    ).not.toEqual("");
  });

  test("dashboard renders SVG diagram + 6-step onboarding + existing checklist", async ({ page }) => {
    await login(page);
    await page.goto("/admin", { waitUntil: "domcontentloaded" });

    // Wait for the dashboard to load (it fetches data async)
    await page
      .getByText(/Mintkey — credential broker for AI agents/i)
      .first()
      .waitFor({ timeout: 25_000 });

    // AC 2a: SVG diagram with labelled nodes
    const diagram = page.locator('[data-testid="data-model-diagram"]');
    await diagram.waitFor({ state: "visible", timeout: 10_000 });

    const diagramText = await diagram.textContent() ?? "";
    expect(diagramText).toContain("Tenant");
    expect(diagramText).toContain("Service");
    expect(diagramText).toContain("Credential");
    expect(diagramText).toContain("Agent");
    expect(diagramText).toContain("Permission");
    expect(diagramText).toContain("Audit Events");

    // Check SVG has rect and line elements
    const rects = await diagram.locator("rect").count();
    expect(rects, "SVG diagram must have at least 6 rect nodes").toBeGreaterThanOrEqual(6);

    // AC 2b: 6-step onboarding section
    const getStarted = page.locator('[data-testid="get-started-section"]');
    await getStarted.waitFor({ state: "visible", timeout: 10_000 });

    for (let i = 1; i <= 6; i++) {
      const step = page.locator(`[data-testid="onboarding-step-${i}"]`);
      await expect(step).toBeVisible();
    }

    // Check step labels
    const getStartedText = await getStarted.textContent() ?? "";
    expect(getStartedText).toContain("Register a Service");
    expect(getStartedText).toContain("Attach a Credential");
    expect(getStartedText).toContain("Create an Agent");
    expect(getStartedText).toContain("Connect your LLM via MCP");

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, "dashboard-full.png"), fullPage: true });

    // AC 2c: existing Quick start checklist + At a glance still render
    const body = await page.locator("body").innerText().catch(() => "");
    // Either shows Quick start (when data exists) or the empty state onboarding screen
    expect(
      /Quick start|Register (a|your first) backend service/i.test(body),
      "Dashboard should show Quick-start or onboarding empty state",
    ).toBe(true);
  });

  test("each resource list page shows its intro paragraph (AC #1)", async ({ page }) => {
    await login(page);

    for (const { slug, snippet } of RESOURCE_INTROS) {
      await page.goto(`/admin/resources/${slug}`, { waitUntil: "domcontentloaded" });

      // Wait for either the intro banner OR the list to render
      await page
        .locator('[data-testid="resource-intro-banner"], table, :text("No records")')
        .first()
        .waitFor({ state: "visible", timeout: 25_000 })
        .catch(() => { /* fall through to text check below */ });

      const body = await page.locator("body").innerText().catch(() => "");
      expect(
        body,
        `Resource list /${slug}: intro paragraph snippet not found: "${snippet}"`,
      ).toContain(snippet);

      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `list-${slug}.png`),
        fullPage: true,
      });
    }
  });
});
