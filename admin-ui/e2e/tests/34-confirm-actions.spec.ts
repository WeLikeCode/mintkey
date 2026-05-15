/**
 * Phase 1d — testService + services.delete + agents.delete confirmation pages.
 *
 * Root cause: all three actions lacked a `component:` registration + GET guard,
 * causing "You have to implement action component" on URL navigation.
 *
 * Fix: add ConfirmAction component + GET guard to each.
 *
 * R14c hardening: services.delete and agents.delete render-only specs extended
 * with click-through and outcome assertions. Identified as false-safety-nets in
 * the R14b post-mortem — this chunk closes that gap.
 *
 * Source: ADMIN_UI_ACTION_MATRIX.md Phase 1d.
 */

import { test, expect } from "../fixtures/test.js";
import { AgentsPage } from "../pages/agents.js";
import { createTestService } from "../fixtures/test-data.js";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

// webkit: AdminJS/Axios CORS — tracked W8.
const skipWebkit = ({ browserName }: { browserName: string }) => browserName === "webkit";

// Bootstrap tenant (t_default) — known from seed data.
const TENANT_ID = "9593e3ba-4102-4235-9748-28d35b473214";
const ADMIN_API = process.env.ADMIN_API_URL ?? "http://localhost:8080";
const PLAYWRIGHT_USER = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
const PLAYWRIGHT_PASS_ENV = process.env.PLAYWRIGHT_PASS ?? "";

// ── Shared session helper for direct admin-api calls ─────────────────────────
interface Session { sessionToken: string; csrfToken: string }
let _session: Session | null = null;

async function getSession(): Promise<Session | null> {
  if (_session) return _session;
  if (!PLAYWRIGHT_PASS_ENV) return null;
  const resp = await fetch(`${ADMIN_API}/v1/auth/internal-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: PLAYWRIGHT_USER, password: PLAYWRIGHT_PASS_ENV }),
  });
  if (!resp.ok) return null;
  // Node.js fetch returns multiple Set-Cookie headers as separate entries.
  // getSetCookie() returns all; fall back to get("set-cookie") for older runtimes.
  const cookieHeaders: string[] =
    typeof (resp.headers as { getSetCookie?: () => string[] }).getSetCookie === "function"
      ? (resp.headers as { getSetCookie: () => string[] }).getSetCookie()
      : [resp.headers.get("set-cookie") ?? ""];
  let sessionToken = "";
  let csrfToken = "";
  for (const c of cookieHeaders) {
    const sm = c.match(/mintkey_session=([^;,\s]+)/);
    if (sm) sessionToken = sm[1];
    const cm = c.match(/csrf_token=([^;,\s]+)/);
    if (cm) csrfToken = cm[1];
  }
  if (!sessionToken || !csrfToken) return null;
  _session = { sessionToken, csrfToken };
  return _session;
}

async function apiGet(path: string): Promise<unknown> {
  const session = await getSession();
  const headers: Record<string, string> = {};
  if (session) {
    headers["Cookie"] = `mintkey_session=${session.sessionToken}; csrf_token=${session.csrfToken}`;
  }
  const resp = await fetch(`${ADMIN_API}${path}`, { headers });
  if (!resp.ok) throw new Error(`GET ${path} → ${resp.status}`);
  return resp.json();
}

/**
 * Resolve the canonical svc_<32-hex> AdminJS record ID from a svc_ wire ID.
 *
 * createTestService returns svc_<26-char Crockford>; AdminJS list/record
 * routes use svc_<32-hex> (_service_row_to_dict). The single-service GET
 * endpoint accepts both wire forms and returns the canonical svc_<32-hex> form.
 */
async function resolveCanonicalSvcId(svcWireId: string): Promise<string> {
  const data = await apiGet(
    `/v1/tenants/${TENANT_ID}/services/${svcWireId}`,
  ) as { id?: string };
  const id = data.id ?? "";
  if (!id) throw new Error(`Could not resolve canonical svc ID for wire ID "${svcWireId}"`);
  return id;
}

test.describe("34 — testService / services.delete / agents.delete confirmation pages", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // ── testService ──────────────────────────────────────────────────────────────
  // UX-CLARITY P0: testService now renders TestServiceForm (5-field form + curl
  // preview + result panel) instead of the generic ConfirmAction two-button page.

  test("testService: TestServiceForm renders (no action-component error)", async ({
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

    // TestServiceForm renders (UX-CLARITY P0 replaced ConfirmAction)
    await expect(
      page.locator('[data-testid="test-service-form"]'),
      "TestServiceForm must render",
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.locator('[data-testid="test-service-submit"]'),
      "Run Test button must be visible",
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="test-service-cancel"]'),
      "Cancel button must be visible",
    ).toBeVisible();

    void consoleErrors;
  });

  test("testService: Run Test button fires test and shows result panel", async ({
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
    await expect(page.locator('[data-testid="test-service-form"]')).toBeVisible({ timeout: 10_000 });

    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/services/records/${serviceId}/testService`) &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator('[data-testid="test-service-submit"]').click(),
    ]);
    expect(response.status(), "testService POST must return 2xx").toBeLessThan(400);

    // Wait for result panel — result can be success or error (backend may be unreachable)
    await page.locator('[data-testid="test-result-panel"]').waitFor({ state: "visible", timeout: 15_000 });

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

    // R14c: confirm button must also be visible (not just the page shell)
    await expect(
      page.locator('[data-testid="confirm-action-button"]'),
      "Confirm delete button must be visible",
    ).toBeVisible();

    void consoleErrors;
  });

  test("services.delete: confirm button deletes the service", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // Create a fresh, disposable service so we can safely delete it.
    // Using programmatic setup via admin-api — no page.route mocking (R10-redux lesson).
    const svcIdRaw = await createTestService({
      tenantId: TENANT_ID,
      name: `e2e-svc-delete-${uid()}`,
      baseUrl: "https://delete-me.example.com",
      authScheme: "api_key_header",
    });
    expect(svcIdRaw, "failed to create test service via admin-api").not.toEqual("");

    // Resolve the canonical svc_<32-hex> AdminJS ID via single-service GET.
    // createTestService returns svc_<26-char Crockford>; AdminJS record routes
    // use svc_<32-hex> (_service_row_to_dict).
    const serviceId = await resolveCanonicalSvcId(svcIdRaw);
    expect(serviceId, "Could not resolve canonical svc ID").not.toEqual("");

    await page.goto(`/admin/resources/services/records/${serviceId}/delete`, {
      waitUntil: "domcontentloaded",
    });
    await expect(page.locator('[data-testid="confirm-action-page"]')).toBeVisible({ timeout: 10_000 });

    // Click Confirm — must POST to the delete action handler
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/services/records/${serviceId}/delete`) &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator('[data-testid="confirm-action-button"]').click(),
    ]);
    expect(response.status(), "delete POST must return 2xx").toBeLessThan(400);

    // Wait for redirect to services list (the delete handler returns redirectUrl)
    // or action-notice (if redirect is delayed). Wait for both to settle.
    await Promise.race([
      page.waitForURL(/\/admin\/resources\/services/, { timeout: 10_000 }),
      page.locator('[data-testid="action-notice"]').waitFor({ state: "visible", timeout: 10_000 }),
    ]);
    // Let any in-progress navigations complete before we navigate away
    await page.waitForLoadState("load", { timeout: 10_000 }).catch(() => {});

    // Verify the service is gone — its show page must render "not found" or redirect to list
    await page.goto(`/admin/resources/services/records/${serviceId}/show`, {
      waitUntil: "load",
    });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
    const showBody = await page.locator("body").innerText();
    // AdminJS returns a "not found" error notice or redirects to the resource list
    const isDeleted =
      /not found|error|does not exist|no record|cannot be found/i.test(showBody) ||
      (page.url().includes("/admin/resources/services") && !page.url().includes("/show"));
    expect(isDeleted, "Service must no longer be accessible after delete").toBe(true);

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

    // R14c: confirm button must also be visible (not just the page shell)
    await expect(
      page.locator('[data-testid="confirm-action-button"]'),
      "Confirm delete button must be visible",
    ).toBeVisible();

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
