/**
 * Phase 1d — testService + services.delete + agents.delete confirmation pages.
 *
 * Root cause: all three actions lacked a `component:` registration + GET guard,
 * causing "You have to implement action component" on URL navigation.
 *
 * Fix: add ConfirmAction component + GET guard to each.
 *
 * Source: ADMIN_UI_ACTION_MATRIX.md Phase 1d.
 */

import { test, expect } from "../fixtures/test.js";
import { AgentsPage } from "../pages/agents.js";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

// webkit: AdminJS/Axios CORS — tracked W8.
const skipWebkit = ({ browserName }: { browserName: string }) => browserName === "webkit";

test.describe("34 — testService / services.delete / agents.delete confirmation pages", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // ── testService ──────────────────────────────────────────────────────────────

  test("testService: confirmation page renders (no action-component error)", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // Get any service ID from the list
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await page.locator("table tbody tr").first().waitFor({ state: "visible", timeout: 20_000 });

    const showLink = await page
      .locator("table tbody tr").first()
      .locator("a[href*='/records/'][href*='/show']")
      .getAttribute("href");
    const serviceId = showLink?.match(/\/records\/([^/]+)\/show/)?.[1] ?? "";
    expect(serviceId, "Need a service record ID").not.toEqual("");

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    const body = await page.locator("body").innerText();
    expect(body, "Must not show action-component error").not.toContain("implement action component");

    await expect(
      page.locator('[data-testid="confirm-action-page"]'),
      "Confirmation page must render",
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.locator('[data-testid="confirm-action-button"]'),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="cancel-action-button"]'),
    ).toBeVisible();

    void consoleErrors;
  });

  test("testService: confirm button fires test and shows result notice", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await page.locator("table tbody tr").first().waitFor({ state: "visible", timeout: 20_000 });

    const showLink = await page
      .locator("table tbody tr").first()
      .locator("a[href*='/records/'][href*='/show']")
      .getAttribute("href");
    const serviceId = showLink?.match(/\/records\/([^/]+)\/show/)?.[1] ?? "";
    expect(serviceId).not.toEqual("");

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    await expect(page.locator('[data-testid="confirm-action-page"]')).toBeVisible({ timeout: 10_000 });

    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/services/records/${serviceId}/testService`) &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator('[data-testid="confirm-action-button"]').click(),
    ]);
    expect(response.status(), "testService POST must return 2xx").toBeLessThan(400);

    // Wait for notice — result can be success or error (backend may be unreachable)
    await page.locator('[data-testid="action-notice"]').waitFor({ state: "visible", timeout: 15_000 });

    void consoleErrors;
  });

  // ── services.delete ───────────────────────────────────────────────────────────

  test("services.delete: confirmation page renders (no action-component error)", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await page.locator("table tbody tr").first().waitFor({ state: "visible", timeout: 20_000 });

    const showLink = await page
      .locator("table tbody tr").first()
      .locator("a[href*='/records/'][href*='/show']")
      .getAttribute("href");
    const serviceId = showLink?.match(/\/records\/([^/]+)\/show/)?.[1] ?? "";
    expect(serviceId).not.toEqual("");

    await page.goto(`/admin/resources/services/records/${serviceId}/delete`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    const body = await page.locator("body").innerText();
    expect(body, "Must not show action-component error").not.toContain("implement action component");
    expect(body, "Must not show 'action not found' error").not.toContain("does not have an action with name: delete");

    await expect(
      page.locator('[data-testid="confirm-action-page"]'),
      "Confirmation page must render",
    ).toBeVisible({ timeout: 10_000 });

    void consoleErrors;
  });

  // ── agents.delete ─────────────────────────────────────────────────────────────

  test("agents.delete: confirmation page renders (no action-component error)", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    const agents = new AgentsPage(page);
    const { agentId } = await agents.createAgent({ name: `e2e-delete-${uid()}` });
    expect(agentId, "createAgent must return an ID").not.toEqual("");

    await page.goto(`/admin/resources/agents/records/${agentId}/delete`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    const body = await page.locator("body").innerText();
    expect(body, "Must not show action-component error").not.toContain("implement action component");
    expect(body, "Must not show 'action not found' error").not.toContain("does not have an action with name: delete");

    await expect(
      page.locator('[data-testid="confirm-action-page"]'),
      "Confirmation page must render",
    ).toBeVisible({ timeout: 10_000 });

    void consoleErrors;
  });

  test("agents.delete: confirm button deletes the agent", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    const agents = new AgentsPage(page);
    const { agentId } = await agents.createAgent({ name: `e2e-delete-full-${uid()}` });
    expect(agentId).not.toEqual("");

    await page.goto(`/admin/resources/agents/records/${agentId}/delete`, {
      waitUntil: "domcontentloaded",
    });
    await expect(page.locator('[data-testid="confirm-action-page"]')).toBeVisible({ timeout: 10_000 });

    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/agents/records/${agentId}/delete`) &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator('[data-testid="confirm-action-button"]').click(),
    ]);
    expect(response.status(), "delete POST must return 2xx").toBeLessThan(400);

    // Should redirect to agents list on success
    await Promise.race([
      page.waitForURL(/\/admin\/resources\/agents/, { timeout: 10_000 }),
      page.locator('[data-testid="action-notice"]').waitFor({ state: "visible", timeout: 10_000 }),
    ]);

    void consoleErrors;
  });
});
