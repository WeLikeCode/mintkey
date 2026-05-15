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
 * R14c hardening: rotateCredential render-only spec extended with click-through
 * and DB side-effect assertion (superseded old key, new active key). Identified as
 * false-safety-net in R14b post-mortem — this chunk closes that gap.
 *
 * Source: ADMIN_UI_ACTION_MATRIX.md Phase 1b; ADR-0013; T-1.4.3; T-1.8.4.
 */

import { test, expect } from "../fixtures/test.js";
import { AgentsPage } from "../pages/agents.js";
import { createTestService, createTestCredential } from "../fixtures/test-data.js";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 5);

// webkit: AdminJS/Axios CORS — tracked W8.
const skipWebkit = ({ browserName }: { browserName: string }) => browserName === "webkit";

// Bootstrap tenant (t_default) — known from seed data.
const TENANT_ID = "9593e3ba-4102-4235-9748-28d35b473214";
const ADMIN_API = process.env.ADMIN_API_URL ?? "http://localhost:8080";
const PLAYWRIGHT_USER = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
const PLAYWRIGHT_PASS = process.env.PLAYWRIGHT_PASS ?? "";

// ── Shared session helper for direct admin-api calls ─────────────────────────

interface Session { sessionToken: string; csrfToken: string }
let _session: Session | null = null;

async function getSession(): Promise<Session | null> {
  if (_session) return _session;
  if (!PLAYWRIGHT_PASS) return null;
  const resp = await fetch(`${ADMIN_API}/v1/auth/internal-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: PLAYWRIGHT_USER, password: PLAYWRIGHT_PASS }),
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

    // R14c: confirm button must also be visible (not just the page shell)
    await expect(
      page.locator('[data-testid="confirm-action-button"]'),
      "Confirm button must be visible on rotate page",
    ).toBeVisible();

    void consoleErrors;
  });

  // ── rotateCredential: click-through + DB side-effect (R14c) ─────────────

  test("rotateCredential: confirm button rotates credential — success notice + DB side-effect", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // ── Setup: create a fresh service + initial credential via admin-api ────
    // Using programmatic setup so the test is fully self-contained and not
    // dependent on pre-seeded data. Real admin-api — no page.route mocking.
    const svcIdRaw = await createTestService({
      tenantId: TENANT_ID,
      name: `e2e-rotate-svc-${uid()}`,
      baseUrl: "https://rotate.example.com",
      authScheme: "bearer_token",
    });
    expect(svcIdRaw, "failed to create test service via admin-api").not.toEqual("");

    // ── Resolve canonical svc_<32-hex> + UUID BEFORE creating credential ────
    // createTestService returns svc_<26-char Crockford>; the credentials POST
    // endpoint requires service_id as a UUID (not wire form). The credentials
    // list endpoint also requires a UUID. Resolve both from the single-service GET
    // (which accepts both wire forms and returns the canonical svc_<32-hex> form).
    const svcDetailData = await apiGet(
      `/v1/tenants/${TENANT_ID}/services/${svcIdRaw}`,
    ) as { id?: string };
    const svcId = svcDetailData.id ?? "";  // canonical svc_<32-hex> for AdminJS routes
    expect(svcId, "Could not resolve canonical svc ID via single-service GET").not.toEqual("");
    expect(svcId, "Canonical svc ID must be svc_<32-hex>").toMatch(/^svc_[0-9a-f]{32}$/);

    // Convert svc_<32-hex> → UUID for direct admin-api endpoints that require UUID path params
    const hexTail = svcId.slice(4);  // strip "svc_" prefix
    const svcUuid = `${hexTail.slice(0, 8)}-${hexTail.slice(8, 12)}-${hexTail.slice(12, 16)}-${hexTail.slice(16, 20)}-${hexTail.slice(20)}`;

    await createTestCredential({
      tenantId: TENANT_ID,
      serviceId: svcUuid,  // credentials POST requires UUID, not svc_ wire form
      authScheme: "bearer_token",
      plaintext: `initial-secret-${uid()}`,
    });

    // ── Navigate to rotateCredential action ─────────────────────────────────
    await page.goto(`/admin/resources/credentials/records/${svcId}/rotateCredential`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    await expect(
      page.locator('[data-testid="confirm-action-page"]'),
      "Rotate confirmation page must render",
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.locator('[data-testid="confirm-action-button"]'),
      "Confirm rotate button must be visible",
    ).toBeVisible();

    // ── Click Confirm — must POST to the rotateCredential action handler ────
    // No page.route: hits real admin-api (R10-redux lesson).
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/credentials/records/${svcId}/rotateCredential`) &&
          r.request().method() === "POST",
        { timeout: 20_000 },
      ),
      page.locator('[data-testid="confirm-action-button"]').click(),
    ]);
    expect(response.status(), "rotateCredential POST must return 2xx").toBeLessThan(400);

    // ── Assert success via the API response notice type ───────────────────────
    // The ConfirmAction component passes data.notice.type directly from the handler.
    // Check the response body: notice.type must be "success", not "error".
    const responseBody = await response.json() as {
      notice?: { type?: string; message?: string };
    };
    expect(
      responseBody.notice?.type,
      `rotateCredential handler must return success notice, got: ${JSON.stringify(responseBody.notice)}`,
    ).toBe("success");

    // ── Also wait for the UI notice to be visible ──────────────────────────────
    await page.locator('[data-testid="action-notice"]').waitFor({ state: "visible", timeout: 15_000 });
    const noticeText = await page.locator('[data-testid="action-notice"]').innerText();
    expect(
      noticeText.toLowerCase(),
      "UI notice must confirm rotation succeeded (not error)",
    ).toMatch(/rotat|success|done|credential/i);

    // ── Assert DB side-effect via admin-api list-credentials ────────────────
    // After rotate, the service should have:
    //   key_version=1  → status="superseded"
    //   key_version=2  → status="active"
    // This exercises the real backend (R14a) end-to-end.
    // svcUuid is already computed above (UUID form required by credentials endpoint).
    const credsData = await apiGet(
      `/v1/tenants/${TENANT_ID}/services/${svcUuid}/credentials`,
    ) as { versions?: Array<{ key_version: number; status: string }> };

    const versions = credsData.versions ?? [];
    expect(versions.length, "Must have at least 2 credential versions after rotation").toBeGreaterThanOrEqual(2);

    const active = versions.filter((v) => v.status === "active");
    const superseded = versions.filter((v) => v.status === "superseded");

    expect(active.length, "Exactly one active credential after rotation").toBe(1);
    expect(superseded.length, "At least one superseded credential after rotation").toBeGreaterThanOrEqual(1);

    // The new active version must be strictly higher than the superseded one
    expect(
      active[0].key_version,
      "Active key_version must be higher than superseded key_version",
    ).toBeGreaterThan(superseded[0].key_version);

    void consoleErrors;
  });
});
