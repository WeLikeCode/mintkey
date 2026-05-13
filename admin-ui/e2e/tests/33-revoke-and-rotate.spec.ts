/**
 * Phase 1b — revokeAgent + rotateCredential confirmation pages.
 *
 * Root cause: both custom record actions lack a `component:` registration and a
 * `request.method === "get"` guard, so navigating to the action URL:
 *   1. Fires the real API call on GET (destructive side-effect without confirmation).
 *   2. Renders "You have to implement action component for your ActionSee: the docs".
 *
 * Fix: add ConfirmAction React component + GET guard to both handlers.
 *
 * Source: ADMIN_UI_ACTION_MATRIX.md Phase 1b; ADR-0013; T-1.4.3; T-1.8.4.
 */

import { test, expect } from "../fixtures/test.js";
import { AgentsPage } from "../pages/agents.js";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

// webkit: AdminJS/Axios CORS — tracked W8.
const skipWebkit = ({ browserName }: { browserName: string }) => browserName === "webkit";

test.describe("33 — revokeAgent / rotateCredential confirmation pages", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // ── revokeAgent ──────────────────────────────────────────────────────────

  test("revokeAgent: confirmation page renders (no action-component error)", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");
    const agents = new AgentsPage(page);
    const { agentId } = await agents.createAgent({ name: `e2e-revoke-${uid()}` });
    expect(agentId, "createAgent must return an ID").not.toEqual("");

    await page.goto(`/admin/resources/agents/records/${agentId}/revokeAgent`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    const body = await page.locator("body").innerText();
    expect(body, "Must not show action-component error").not.toContain("implement action component");
    expect(body, "Must not show pre-confirmation API error").not.toContain("Revocation failed");

    await expect(
      page.locator('[data-testid="confirm-action-page"]'),
      "Confirmation page must render",
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.locator('[data-testid="confirm-action-button"]'),
      "Confirm button must be visible",
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="cancel-action-button"]'),
      "Cancel button must be visible",
    ).toBeVisible();

    void consoleErrors;
  });

  test("revokeAgent: confirm button revokes the agent", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");
    const agents = new AgentsPage(page);
    const { agentId } = await agents.createAgent({ name: `e2e-revoke-full-${uid()}` });
    expect(agentId, "createAgent must return an ID").not.toEqual("");

    await page.goto(`/admin/resources/agents/records/${agentId}/revokeAgent`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    // Confirmation page must be shown first (no pre-confirmation API call)
    await expect(page.locator('[data-testid="confirm-action-page"]')).toBeVisible({ timeout: 10_000 });

    // Click Confirm — this should POST to the action handler
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/agents/records/${agentId}/revokeAgent`) &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator('[data-testid="confirm-action-button"]').click(),
    ]);
    expect(response.status(), "revoke POST must return 2xx").toBeLessThan(400);

    // Wait for success notice or navigation to list
    await Promise.race([
      page.locator('[data-testid="action-notice"]').waitFor({ state: "visible", timeout: 10_000 }),
      page.waitForURL(/\/admin\/resources\/agents/, { timeout: 10_000 }),
    ]);

    // Verify the agent is now revoked by checking the show page
    await agents.gotoShow(agentId);
    await page.waitForLoadState("networkidle");
    const showBody = await page.locator("body").innerText();
    expect(showBody, "agent show page must contain 'revoked'").toContain("revoked");

    void consoleErrors;
  });

  // ── rotateCredential ─────────────────────────────────────────────────────

  test("rotateCredential: confirmation page renders (no action-component error)", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // Navigate to credentials list and get a service ID (credentials list reuses services endpoint)
    await page.goto("/admin/resources/credentials", { waitUntil: "domcontentloaded" });
    await page.locator("table tbody tr").first().waitFor({ state: "visible", timeout: 20_000 });

    const showLink = await page
      .locator("table tbody tr")
      .first()
      .locator("a[href*='/records/'][href*='/show']")
      .getAttribute("href");
    const match = showLink?.match(/\/records\/([^/]+)\/show/);
    const serviceId = match?.[1] ?? "";
    expect(serviceId, "Need a service record ID to test rotateCredential").not.toEqual("");

    // Navigate to rotateCredential action
    await page.goto(`/admin/resources/credentials/records/${serviceId}/rotateCredential`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    const body = await page.locator("body").innerText();
    expect(body, "Must not show action-component error").not.toContain("implement action component");
    // Before the GET guard fix: the handler fires on GET and returns a validation error
    expect(body, "Must not show pre-confirmation validation error").not.toContain("validation errors");

    await expect(
      page.locator('[data-testid="confirm-action-page"]'),
      "Confirmation page must render",
    ).toBeVisible({ timeout: 10_000 });

    void consoleErrors;
  });
});
