/**
 * W0 migration: intros and dashboard UX uplift.
 *
 * Migrated from admin-ui/tests/e2e/intros-and-dashboard.spec.ts.
 * Verifies the SVG data-model diagram, 6-step onboarding section, and
 * per-resource intro paragraphs above each resource list.
 *
 * Source: admin-ui-ux-uplift acceptance criteria #1, #2, #5; ADR-0019.
 */

import { test, expect } from "../fixtures/test.js";

const RESOURCE_INTROS: Array<{ slug: string; snippet: string }> = [
  { slug: "tenants", snippet: "Tenants are isolated workspaces." },
  { slug: "services", snippet: "Services are the backend APIs you" },
  { slug: "credentials", snippet: "Credentials are the real secrets" },
  { slug: "agents", snippet: "Agents are the AI agents" },
  { slug: "permission_grants", snippet: "Permission Grants tie an Agent" },
  { slug: "service_api_keys", snippet: "Service API Keys" },
  { slug: "audit_events", snippet: "Audit Events are the immutable" },
];

test.describe("27 — Intros and dashboard UX uplift", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS env var is required").not.toEqual("");
  });

  test("dashboard: SVG data-model diagram + 6-step onboarding + existing checklist", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page
      .getByText(/Mintkey — credential broker for AI agents/i)
      .first()
      .waitFor({ timeout: 25_000 });

    const diagram = page.locator('[data-testid="data-model-diagram"]');
    await diagram.waitFor({ state: "visible", timeout: 10_000 });

    const diagramText = (await diagram.textContent()) ?? "";
    expect(diagramText).toContain("Tenant");
    expect(diagramText).toContain("Service");
    expect(diagramText).toContain("Credential");
    expect(diagramText).toContain("Agent");
    expect(diagramText).toContain("Permission");
    expect(diagramText).toContain("Audit Events");

    const rects = await diagram.locator("rect").count();
    expect(rects, "SVG diagram must have ≥6 rect nodes").toBeGreaterThanOrEqual(6);

    const getStarted = page.locator('[data-testid="get-started-section"]');
    await getStarted.waitFor({ state: "visible", timeout: 10_000 });
    for (let i = 1; i <= 6; i++) {
      await expect(page.locator(`[data-testid="onboarding-step-${i}"]`)).toBeVisible();
    }

    const getStartedText = (await getStarted.textContent()) ?? "";
    expect(getStartedText).toContain("Register a Service");
    expect(getStartedText).toContain("Attach a Credential");
    expect(getStartedText).toContain("Create an Agent");
    expect(getStartedText).toContain("Connect your LLM via MCP");

    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(
      /Quick start|Register (a|your first) backend service/i.test(body),
      "Dashboard should show Quick-start or onboarding empty state",
    ).toBe(true);

    void consoleErrors;
  });

  test("each resource list page shows its intro paragraph", async ({ page, consoleErrors }) => {
    for (const { slug, snippet } of RESOURCE_INTROS) {
      await page.goto(`/admin/resources/${slug}`, { waitUntil: "domcontentloaded" });
      await page
        .locator('[data-testid="resource-intro-banner"], table, :text("No records")')
        .first()
        .waitFor({ state: "visible", timeout: 25_000 })
        .catch(() => {});

      const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
      expect(
        body,
        `Resource list /${slug}: intro paragraph snippet not found: "${snippet}"`,
      ).toContain(snippet);
    }
    void consoleErrors;
  });
});
