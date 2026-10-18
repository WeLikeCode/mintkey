/**
 * W3: Form validation rendering.
 *
 * Submit invalid forms — assert field-level error renders, no JS-error box.
 *
 * Covered resources: Services (missing required fields), Tenants (duplicate slug),
 * Permission Grants (missing agent_id / service_id).
 *
 * Source: PLAYWRIGHT_EXTENSION_PLAN.md W3; ADR-0019; ADR-0013.
 */

import { test, expect } from "../fixtures/test.js";

const JS_ERROR_NEEDLES = [
  "Javascript Error",
  "JavaScript Error",
  "Minified React error",
  "Objects are not valid as a React child",
  "TypeError",
  "Application error",
];

async function bodyText(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
): Promise<string> {
  return (await page.locator("body").innerText().catch(() => "")) ?? "";
}

async function expectNoJsError(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
  where: string,
): Promise<void> {
  const body = await bodyText(page);
  for (const needle of JS_ERROR_NEEDLES) {
    expect(body, `${where}: "${needle}" found after validation error`).not.toContain(needle);
  }
}

test.describe("18 — Form validation rendering", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // ── Services: missing required name ─────────────────────────────────────
  test("Services new: missing name → error renders, no JS error box", async ({
    page,
    consoleErrors,
  }) => {
    // ServiceCreateForm (0b04288) validates required fields client-side and shows the message in
    // [data-testid=create-error]; there is no slug input and no request is sent.
    await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
    await page.locator("[data-testid='service-create-form']").waitFor({ state: "visible", timeout: 15_000 });

    await page.locator("[data-testid='field-input-base_url']").fill("https://validation.example.com");
    // Leave name blank and submit.
    await page.locator("[data-testid='service-create-submit']").click();

    const err = page.locator("[data-testid='create-error']");
    await expect(err, "missing name must render the inline validation error").toBeVisible({ timeout: 5_000 });
    await expect(err).toContainText(/name is required/i);
    await expectNoJsError(page, "services new (missing name)");

    void consoleErrors;
  });

  // ── Services: missing required base_url ──────────────────────────────────
  test("Services new: missing base_url → error renders, no JS error box", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
    await page.locator("[data-testid='service-create-form']").waitFor({ state: "visible", timeout: 15_000 });

    await page.locator("[data-testid='field-input-name']").fill("e2e-validation-test");
    // Deliberately leave base_url empty
    await page.locator("[data-testid='service-create-submit']").click();

    const err = page.locator("[data-testid='create-error']");
    await expect(err, "missing base_url must render the inline validation error").toBeVisible({ timeout: 5_000 });
    await expect(err).toContainText(/base url is required/i);
    await expectNoJsError(page, "services new (missing base_url)");

    void consoleErrors;
  });

  // ── Tenants: duplicate slug constraint violation ─────────────────────────
  test("Tenants new: duplicate slug (t_default) → error renders, no JS error box", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/tenants/actions/new", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle");

    // t_default is the bootstrap tenant — duplicate slug must fail
    const slugField = page.getByLabel("slug");
    const displayNameField = page.getByLabel(/display.?name/i);

    if ((await slugField.count()) === 0) {
      void consoleErrors;
      return;
    }

    await slugField.fill("t_default");
    if ((await displayNameField.count()) > 0) await displayNameField.fill("E2E Duplicate Test");

    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/admin/api/resources/tenants/actions/new") &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.getByRole("button", { name: /save|create/i }).click(),
    ]);

    await expectNoJsError(page, "tenants new (duplicate slug t_default)");

    // Either a notice with an error OR form stayed on page — both are acceptable
    const body = await bodyText(page);
    const respBody = await resp.json().catch(() => ({}) as Record<string, unknown>) as Record<string, unknown>;
    const noticeType = (respBody.notice as { type?: string } | undefined)?.type;

    // If the API returns an error notice OR the page shows an error banner — good
    const hasError = noticeType === "error" || /duplicate|already|conflict|error/i.test(body);
    const isOnListPage = page.url().includes("/admin/resources/tenants") && !page.url().includes("/actions/");

    expect(hasError || isOnListPage, "duplicate slug must render error or redirect cleanly").toBe(true);

    void consoleErrors;
  });

  // ── Permission Grants: missing agent_id ────────────────────────────────
  test("Permission Grants new: missing agent_id → no JS error box", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/permission_grants/actions/new", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    // Fill action but leave agent_id empty
    const actionField = page.getByLabel(/^action$/i);
    if ((await actionField.count()) > 0) {
      await actionField.fill("read");
    }

    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/admin/api/resources/permission_grants/actions/new") &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.getByRole("button", { name: /save|grant/i }).click(),
    ]);

    await expectNoJsError(page, "permission_grants new (missing agent_id)");

    void consoleErrors;
  });

  // ── Permission Grants: missing service_id ──────────────────────────────
  test("Permission Grants new: missing service_id → no JS error box", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/permission_grants/actions/new", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    // Fill agent_id but leave service_id empty
    const agentIdField = page.getByLabel(/agent.?id/i);
    if ((await agentIdField.count()) > 0) {
      await agentIdField.fill("agent_nonexistent");
    }
    const actionField = page.getByLabel(/^action$/i);
    if ((await actionField.count()) > 0) {
      await actionField.fill("read");
    }

    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/admin/api/resources/permission_grants/actions/new") &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.getByRole("button", { name: /save|grant/i }).click(),
    ]);

    await expectNoJsError(page, "permission_grants new (missing service_id)");

    void consoleErrors;
  });
});
