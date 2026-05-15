/**
 * UX-BL2 — ServiceCreateForm E2E tests (live endpoint rewrite).
 *
 * Drops all page.route interception (R10-redux anti-pattern lesson, commit 2e4b5722).
 * Tests hit real AdminJS + admin-api endpoints through the live authenticated stack.
 *
 * Covers:
 *   1. Form renders: visit /admin/resources/services/actions/new, assert ServiceCreateForm mounts.
 *   2. Conditional fields: pick api_key_header → header_name appears; api_key_query → param_name.
 *   3. bearer_token scheme: no hint-fields section.
 *   4. Submit: fill all fields + credential sub-form → submit → URL navigates to show page.
 *   5. Success banner: "Test connection" + "View service" buttons appear.
 *   6. Test CTA href: "Test connection" points to testService action URL.
 *   7. DB side-effects: verify services list contains the new service after creation.
 *
 * Auth: global-setup (PLAYWRIGHT_PASS) logs into AdminJS once; storageState is reused.
 * Cleanup: afterEach attempts DELETE via admin-api (session+CSRF); services with credentials
 *   are PATCHed to status=inactive instead (FK constraint prevents hard-delete — known limitation).
 *
 * Source: UX-BL2; ServiceCreateForm.tsx; ADMIN_UI_SPEC.md §1.3; R10-redux post-mortem.
 */

import { test, expect } from "../fixtures/test.js";
import { ServicesPage } from "../pages/services.js";

// ── helpers ───────────────────────────────────────────────────────────────────

const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

const ADMIN_API = process.env.ADMIN_API_URL ?? "http://localhost:8080";
const PLAYWRIGHT_USER = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
const TENANT_ID = process.env.MINTKEY_TENANT_ID ?? process.env.PLAYWRIGHT_TENANT_ID ?? "9593e3ba-4102-4235-9748-28d35b473214";

// ── Crockford → UUID conversion (post-#13 ULID wire form) ─────────────────────
const _CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

function wireToUuid(wireId: string): string {
  const tail = wireId.slice(wireId.indexOf("_") + 1);
  if (tail.length === 26) {
    let val = BigInt(0);
    for (const ch of tail.toUpperCase()) {
      val = (val << BigInt(5)) | BigInt(_CROCKFORD.indexOf(ch));
    }
    val &= (BigInt(1) << BigInt(128)) - BigInt(1);
    const h = val.toString(16).padStart(32, "0");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  throw new Error(`Cannot decode wire ID: ${wireId}`);
}

// ── Session helper (fetch-based, for cleanup API calls) ─────────────────────

interface Session { sessionToken: string; csrfToken: string }
let _session: Session | null = null;

async function getSession(): Promise<Session | null> {
  if (_session) return _session;
  const pass = process.env.PLAYWRIGHT_PASS ?? "";
  if (!pass) return null;

  const resp = await fetch(`${ADMIN_API}/v1/auth/internal-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: PLAYWRIGHT_USER, password: pass }),
  });
  if (!resp.ok) return null;

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

function authHeaders(session: Session): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "Cookie": `mintkey_session=${session.sessionToken}; csrf_token=${session.csrfToken}`,
    "X-Mintkey-Csrf": session.csrfToken,
  };
}

/**
 * Best-effort cleanup for a service created during a test.
 *
 * - Services WITHOUT credentials: hard-delete via DELETE /v1/tenants/{tid}/services/{id}.
 * - Services WITH credentials: PATCH to status=inactive (FK constraint prevents hard-delete;
 *   known limitation — admin-api does not cascade-delete credentials).
 *
 * Both are best-effort (failures are logged, not thrown) to satisfy the "cleanup runs even
 * on test failure" requirement.
 */
async function cleanupService(serviceWireId: string): Promise<void> {
  const session = await getSession();
  if (!session || !serviceWireId) return;

  const headers = authHeaders(session);

  // First attempt: hard-delete (works when no credentials exist)
  try {
    const delResp = await fetch(
      `${ADMIN_API}/v1/tenants/${TENANT_ID}/services/${serviceWireId}`,
      { method: "DELETE", headers }
    );
    if (delResp.ok || delResp.status === 404) return; // deleted or already gone
  } catch { /* fall through */ }

  // Fallback: PATCH to inactive (FK prevents hard-delete when credentials exist)
  try {
    let svcUuid: string;
    try {
      svcUuid = wireToUuid(serviceWireId);
    } catch {
      svcUuid = serviceWireId; // may already be UUID form
    }
    await fetch(
      `${ADMIN_API}/v1/tenants/${TENANT_ID}/services/${svcUuid}`,
      {
        method: "PATCH",
        headers,
        body: JSON.stringify({ status: "inactive" }),
      }
    );
  } catch { /* best-effort */ }
}

/**
 * Verify DB side-effect: the service appears in the admin-api services list.
 * Returns the service object when found, throws if not found within timeout.
 */
async function assertServiceInList(serviceName: string): Promise<{ id: string; name: string }> {
  const session = await getSession();
  if (!session) throw new Error("No session for DB side-effect assertion");

  const resp = await fetch(
    `${ADMIN_API}/v1/tenants/${TENANT_ID}/services?q=${encodeURIComponent(serviceName)}`,
    { headers: authHeaders(session) }
  );
  if (!resp.ok) throw new Error(`Services list returned ${resp.status}`);

  const data = await resp.json() as { services?: Array<{ id: string; name: string }> };
  const found = (data.services ?? []).find((s) => s.name === serviceName);
  if (!found) throw new Error(`Service "${serviceName}" not found in admin-api list`);
  return found;
}

// ── spec ──────────────────────────────────────────────────────────────────────

test.describe("30 — UX-BL2: ServiceCreateForm (real endpoints, no page.route)", () => {
  // webkit: AdminJS/Axios CORS — tracked W8.
  test.skip(({ browserName }) => browserName === "webkit", "webkit CORS W8");

  test.beforeAll(() => {
    expect(
      process.env.PLAYWRIGHT_PASS ?? "",
      "PLAYWRIGHT_PASS env var is required for live-endpoint tests"
    ).not.toEqual("");
  });

  // ── Test 1: Form renders ─────────────────────────────────────────────────────

  test("1: new-service form renders ServiceCreateForm with auth_scheme dropdown", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });

    // The custom ServiceCreateForm mounts when the user is authenticated
    const form = page.locator("[data-testid='service-create-form']");
    await expect(form, "ServiceCreateForm must render for authenticated operator").toBeVisible({ timeout: 15_000 });

    // auth_scheme dropdown must be present
    const schemeSelect = page.locator("[data-testid='field-select-auth_scheme']");
    await expect(schemeSelect, "auth_scheme dropdown must be visible").toBeVisible({ timeout: 5_000 });

    // api_key_header option must be present
    const options = await schemeSelect.locator("option").allTextContents();
    const hasApiKeyHeader = options.some((o) => /api.*key.*header/i.test(o));
    expect(hasApiKeyHeader, "auth_scheme dropdown must include api_key_header").toBe(true);

    // No JS errors on the form page
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    expect(body, "Must not show action-component error").not.toContain("implement action component");
    expect(body, "Must not show JS error").not.toContain("JavaScript Error");

    void consoleErrors;
  });

  // ── Test 2: Conditional fields — api_key_header ──────────────────────────────

  test("2: selecting api_key_header reveals header_name field; api_key_query reveals param_name", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
    const form = page.locator("[data-testid='service-create-form']");
    await expect(form).toBeVisible({ timeout: 15_000 });

    const schemeSelect = page.locator("[data-testid='field-select-auth_scheme']");
    await expect(schemeSelect).toBeVisible({ timeout: 5_000 });

    // Select api_key_header → header_name input must appear
    await schemeSelect.selectOption("api_key_header");
    const headerNameInput = page.locator("[data-testid='field-input-header_name']");
    await expect(headerNameInput, "header_name input must appear for api_key_header").toBeVisible({ timeout: 3_000 });

    // Select api_key_query → header_name disappears, param_name appears
    await schemeSelect.selectOption("api_key_query");
    await expect(headerNameInput, "header_name must disappear for api_key_query").not.toBeVisible({ timeout: 3_000 });
    const paramNameInput = page.locator("[data-testid='field-input-param_name']");
    await expect(paramNameInput, "param_name input must appear for api_key_query").toBeVisible({ timeout: 3_000 });

    void consoleErrors;
  });

  // ── Test 3: bearer_token shows no hint fields ─────────────────────────────────

  test("3: bearer_token scheme shows no scheme-specific hint fields", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
    const form = page.locator("[data-testid='service-create-form']");
    await expect(form).toBeVisible({ timeout: 15_000 });

    const schemeSelect = page.locator("[data-testid='field-select-auth_scheme']");
    await expect(schemeSelect).toBeVisible({ timeout: 5_000 });
    await schemeSelect.selectOption("bearer_token");

    // The auth-scheme-hint-fields section should not appear for bearer_token
    // (bearer_token has no non-secret hint fields — only the secret value field)
    const hintSection = page.locator("[data-testid='auth-scheme-hint-fields']");
    const hintVisible = await hintSection.isVisible().catch(() => false);
    expect(hintVisible, "bearer_token must not show hint-fields section").toBe(false);

    void consoleErrors;
  });

  // ── Test 4: Submit flow + success banner + DB side-effect ────────────────────

  test("4: fill form + api_key_header + credential subform → submit → show page + success banner → DB verified", async ({
    page,
    consoleErrors,
  }) => {
    const svcName = `ux-bl2-service-${uid()}`;
    let createdSvcId = "";

    test.info().annotations.push({ type: "service-name", description: svcName });

    try {
      await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
      const form = page.locator("[data-testid='service-create-form']");
      await expect(form, "ServiceCreateForm must render").toBeVisible({ timeout: 15_000 });

      // Fill service fields
      await page.locator("[data-testid='field-input-name']").fill(svcName);
      await page.locator("[data-testid='field-input-base_url']").fill("https://api.example.com");

      // Select api_key_header scheme
      const schemeSelect = page.locator("[data-testid='field-select-auth_scheme']");
      await schemeSelect.selectOption("api_key_header");

      // Fill header_name hint field
      const headerNameInput = page.locator("[data-testid='field-input-header_name']");
      await expect(headerNameInput, "header_name input must appear").toBeVisible({ timeout: 3_000 });
      await headerNameInput.fill("X-Test-Key");

      // Enable credential sub-form
      const credCheckbox = page.locator("[data-testid='add-credential-checkbox']");
      await credCheckbox.check();

      // Credential subform must appear; fill the secret value
      const credSubform = page.locator("[data-testid='credential-subform']");
      await expect(credSubform, "credential-subform must appear after checkbox").toBeVisible({ timeout: 3_000 });
      const valueInput = page.locator("[data-testid='field-input-value']");
      await valueInput.fill("e2e-test-api-key-secret");

      // Submit — waits for the real admin-api service creation
      const submitBtn = page.locator("[data-testid='service-create-submit']");
      await submitBtn.click();

      // ── Assert success banner (ServiceCreateForm success state) ──────────────
      const successBanner = page.locator("[data-testid='success-banner']");
      await expect(successBanner, "success-banner must appear after submit").toBeVisible({ timeout: 20_000 });

      // "Test connection" CTA must be present
      const testBtn = page.locator("[data-testid='test-connection-btn']");
      await expect(testBtn, "'Test connection' CTA must be visible").toBeVisible({ timeout: 5_000 });

      // "View service" CTA must be present
      const viewBtn = page.locator("[data-testid='skip-to-service-btn']");
      await expect(viewBtn, "'View service' CTA must be visible").toBeVisible({ timeout: 3_000 });

      // ── Extract created service ID from "Test connection" href ───────────────
      const testHref = await testBtn.getAttribute("href") ?? "";
      const idMatch = testHref.match(/records\/([^/]+)\/testService/);
      createdSvcId = idMatch?.[1] ?? "";
      expect(createdSvcId, "Could not extract service ID from test-connection href").not.toEqual("");

      // ── Navigate to show page and confirm it renders the service ─────────────
      const viewHref = await viewBtn.getAttribute("href") ?? "";
      expect(viewHref, "View service href must point to show page").toMatch(/\/records\/[^/]+\/show$/);

      await page.goto(viewHref, { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});

      const showBody = (await page.locator("body").innerText().catch(() => "")) ?? "";
      expect(showBody, "Show page must display the service name").toContain(svcName);
      expect(showBody, "Show page must not show JS errors").not.toContain("JavaScript Error");

      // ── DB side-effect: services list must contain the new service ────────────
      const dbService = await assertServiceInList(svcName);
      expect(dbService.id, "admin-api services list must include created service").not.toEqual("");

      // Store the wire-form ID for cleanup
      if (!createdSvcId) createdSvcId = dbService.id;

    } finally {
      await cleanupService(createdSvcId);
    }

    void consoleErrors;
  });

  // ── Test 5: "Test connection" CTA href points to testService action ──────────

  test("5: 'Test connection' CTA href contains testService action and service ID", async ({
    page,
    consoleErrors,
  }) => {
    const svcName = `ux-bl2-cta-${uid()}`;
    let createdSvcId = "";

    try {
      await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
      const form = page.locator("[data-testid='service-create-form']");
      await expect(form).toBeVisible({ timeout: 15_000 });

      // Fill minimum required fields
      await page.locator("[data-testid='field-input-name']").fill(svcName);
      await page.locator("[data-testid='field-input-base_url']").fill("https://api.example.com");

      // Submit without credential (bearer_token scheme has no creds by default — use none scheme)
      const schemeSelect = page.locator("[data-testid='field-select-auth_scheme']");
      await schemeSelect.selectOption("none");

      await page.locator("[data-testid='service-create-submit']").click();

      const successBanner = page.locator("[data-testid='success-banner']");
      await expect(successBanner, "success-banner must appear").toBeVisible({ timeout: 20_000 });

      const testBtn = page.locator("[data-testid='test-connection-btn']");
      await expect(testBtn, "Test connection CTA must be visible").toBeVisible({ timeout: 5_000 });

      const href = await testBtn.getAttribute("href") ?? "";
      expect(href, "Test connection CTA must link to testService action").toContain("testService");

      // Extract service ID from href
      const idMatch = href.match(/records\/([^/]+)\/testService/);
      createdSvcId = idMatch?.[1] ?? "";
      expect(createdSvcId, "Test connection href must contain a service ID").not.toEqual("");
      expect(href, "Test connection href must contain the created service ID").toContain(createdSvcId);

    } finally {
      await cleanupService(createdSvcId);
    }

    void consoleErrors;
  });

  // ── Test 6: Submit without credential — no success-banner credential warning ──

  test("6: submit with 'none' scheme + no credential → success banner + no credential warning", async ({
    page,
    consoleErrors,
  }) => {
    const svcName = `ux-bl2-no-cred-${uid()}`;
    let createdSvcId = "";

    try {
      await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
      const form = page.locator("[data-testid='service-create-form']");
      await expect(form).toBeVisible({ timeout: 15_000 });

      await page.locator("[data-testid='field-input-name']").fill(svcName);
      await page.locator("[data-testid='field-input-base_url']").fill("https://api.example.com");
      await page.locator("[data-testid='field-select-auth_scheme']").selectOption("none");

      await page.locator("[data-testid='service-create-submit']").click();

      const successBanner = page.locator("[data-testid='success-banner']");
      await expect(successBanner, "success-banner must appear for no-credential submit").toBeVisible({ timeout: 20_000 });

      // No credential-warning section should appear (none scheme → no credential step)
      const credWarning = page.locator("[data-testid='credential-warning']");
      const warnVisible = await credWarning.isVisible().catch(() => false);
      expect(warnVisible, "credential-warning must NOT appear for none scheme").toBe(false);

      // Extract service ID
      const testBtn = page.locator("[data-testid='test-connection-btn']");
      const href = await testBtn.getAttribute("href") ?? "";
      const idMatch = href.match(/records\/([^/]+)\/testService/);
      createdSvcId = idMatch?.[1] ?? "";

      // DB side-effect: service appears in list
      const dbService = await assertServiceInList(svcName);
      expect(dbService.id, "Service must be in admin-api list after creation").not.toEqual("");

    } finally {
      await cleanupService(createdSvcId);
    }

    void consoleErrors;
  });

  // ── Test 7: Validation — name required ─────────────────────────────────────

  test("7: submitting without name shows validation error, does not navigate away", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
    const form = page.locator("[data-testid='service-create-form']");
    await expect(form).toBeVisible({ timeout: 15_000 });

    // Fill base_url but leave name empty
    await page.locator("[data-testid='field-input-base_url']").fill("https://api.example.com");

    await page.locator("[data-testid='service-create-submit']").click();

    // Error box must appear
    const errorBox = page.locator("[data-testid='create-error']");
    await expect(errorBox, "create-error must show when name is missing").toBeVisible({ timeout: 5_000 });

    // Must still be on the new form (no redirect)
    expect(page.url(), "Must stay on new-service URL after validation error").toContain(
      "/admin/resources/services/actions/new"
    );

    void consoleErrors;
  });
});
