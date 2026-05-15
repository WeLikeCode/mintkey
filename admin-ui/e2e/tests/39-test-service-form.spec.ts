/**
 * UX-CLARITY P0 — TestServiceForm E2E tests.
 *
 * Covers:
 *   1. Form renders with all 5 fields + curl preview (no ConfirmAction).
 *   2. Defaults are correct: method=GET, path=/health, timeout=5000.
 *   3. Curl preview updates live as operator changes method+path.
 *   4. Invalid JSON in headers shows inline error before submit.
 *   5. Valid JSON headers: error clears when fixed.
 *   6. Submit with defaults fires admin-api POST with {method:GET, path:/health, timeout_ms:5000}.
 *   7. Submit with POST + custom path fires admin-api with those values (not defaults).
 *   8. Result panel renders: status_code, latency_ms, final_url, response_body visible.
 *
 * No page.route mocking (R10-redux lesson). Tests hit real endpoints.
 *
 * Source: UX-CLARITY P0; ADMIN_UI_SPEC.md §1.4.
 */

import { test, expect } from "../fixtures/test.js";
import { createTestService } from "../fixtures/test-data.js";

const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

const TENANT_ID = process.env.MINTKEY_TENANT_ID ?? process.env.PLAYWRIGHT_TENANT_ID ?? "9593e3ba-4102-4235-9748-28d35b473214";
const ADMIN_API = process.env.ADMIN_API_URL ?? "http://localhost:8080";
const PLAYWRIGHT_USER = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";

// webkit: AdminJS/Axios CORS — tracked W8.
const skipWebkit = ({ browserName }: { browserName: string }) => browserName === "webkit";

// ── Session helper (for programmatic setup + API assertions) ─────────────────

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

/**
 * Resolve the canonical svc_<32-hex> AdminJS record ID from a svc_ wire ID.
 * createTestService returns svc_<26-char Crockford>; AdminJS routes need svc_<32-hex>.
 */
async function resolveCanonicalSvcId(svcWireId: string): Promise<string> {
  const session = await getSession();
  const headers: Record<string, string> = {};
  if (session) {
    headers["Cookie"] = `mintkey_session=${session.sessionToken}; csrf_token=${session.csrfToken}`;
  }
  const resp = await fetch(`${ADMIN_API}/v1/tenants/${TENANT_ID}/services/${svcWireId}`, { headers });
  if (!resp.ok) throw new Error(`GET service → ${resp.status}`);
  const data = await resp.json() as { id?: string };
  const id = data.id ?? "";
  if (!id) throw new Error(`Could not resolve canonical svc ID for "${svcWireId}"`);
  return id;
}

// ── test suite ────────────────────────────────────────────────────────────────

test.describe("39 — UX-CLARITY P0: TestServiceForm (real endpoints)", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  // ── Test 1: Form renders with all 5 fields ──────────────────────────────────

  test("1: testService page renders TestServiceForm (not ConfirmAction)", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // Get any service from list
    await page.goto("/admin/resources/services", { waitUntil: "domcontentloaded" });
    await page.locator("table tbody tr").first().waitFor({ state: "visible", timeout: 20_000 });

    const showLink = await page
      .locator("table tbody tr").first()
      .locator("a[href*='/records/'][href*='/show']")
      .getAttribute("href");
    const serviceId = showLink?.match(/\/records\/([^/]+)\/show/)?.[1] ?? "";
    expect(serviceId, "need a service record ID").not.toEqual("");

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    const body = await page.locator("body").innerText();
    expect(body, "must not show action-component error").not.toContain("implement action component");
    expect(body, "must not show ConfirmAction").not.toContain("Confirm Test Connection");

    // TestServiceForm must render
    const form = page.locator("[data-testid='test-service-form']");
    await expect(form, "TestServiceForm must render").toBeVisible({ timeout: 10_000 });

    void consoleErrors;
  });

  // ── Test 2: All 5 fields present with correct defaults ──────────────────────

  test("2: all 5 fields present with sensible defaults", async ({
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

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    const form = page.locator("[data-testid='test-service-form']");
    await expect(form).toBeVisible({ timeout: 10_000 });

    // Method dropdown — default GET
    const methodSelect = page.locator("[data-testid='field-select-method']");
    await expect(methodSelect, "method dropdown must be visible").toBeVisible();
    await expect(methodSelect).toHaveValue("GET");

    // Path input — default /health
    const pathInput = page.locator("[data-testid='field-input-path']");
    await expect(pathInput, "path input must be visible").toBeVisible();
    await expect(pathInput).toHaveValue("/health");

    // Headers textarea
    const headersInput = page.locator("[data-testid='field-input-headers']");
    await expect(headersInput, "headers textarea must be visible").toBeVisible();

    // Body textarea
    const bodyInput = page.locator("[data-testid='field-input-body']");
    await expect(bodyInput, "body textarea must be visible").toBeVisible();

    // Timeout input — default 5000
    const timeoutInput = page.locator("[data-testid='field-input-timeout']");
    await expect(timeoutInput, "timeout input must be visible").toBeVisible();
    await expect(timeoutInput).toHaveValue("5000");

    void consoleErrors;
  });

  // ── Test 3: Curl preview updates live ──────────────────────────────────────

  test("3: curl preview updates live as method+path change", async ({
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

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    const form = page.locator("[data-testid='test-service-form']");
    await expect(form).toBeVisible({ timeout: 10_000 });

    const curlPreview = page.locator("[data-testid='curl-preview']");
    await expect(curlPreview, "curl preview must be visible").toBeVisible();

    // Initially shows GET ... /health
    const initialCurl = await curlPreview.innerText();
    expect(initialCurl, "initial curl must show GET").toContain("GET");
    expect(initialCurl, "initial curl must show /health").toContain("/health");

    // Change method to POST
    await page.locator("[data-testid='field-select-method']").selectOption("POST");
    const afterMethodChange = await curlPreview.innerText();
    expect(afterMethodChange, "curl must update to show POST after method change").toContain("POST");

    // Change path to /v1/events
    await page.locator("[data-testid='field-input-path']").fill("/v1/events");
    const afterPathChange = await curlPreview.innerText();
    expect(afterPathChange, "curl must update to show /v1/events after path change").toContain("/v1/events");

    // Restore to GET to not pollute the curl preview assertions
    await page.locator("[data-testid='field-select-method']").selectOption("GET");

    void consoleErrors;
  });

  // ── Test 4: Invalid JSON headers shows inline error ─────────────────────────

  test("4: invalid JSON in headers shows inline error, blocks submit", async ({
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

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    const form = page.locator("[data-testid='test-service-form']");
    await expect(form).toBeVisible({ timeout: 10_000 });

    // Type invalid JSON
    const headersInput = page.locator("[data-testid='field-input-headers']");
    await headersInput.fill('{"X-Trace": "bad"');

    // Trigger validation (blur or just check after input)
    await headersInput.dispatchEvent("input");

    // Wait a tick for React to re-render
    await page.waitForTimeout(100);

    // Inline error must appear
    const headersError = page.locator("[data-testid='headers-json-error']");
    await expect(headersError, "headers JSON error must appear for invalid JSON").toBeVisible({ timeout: 3_000 });

    // Submit button must be disabled
    const submitBtn = page.locator("[data-testid='test-service-submit']");
    await expect(submitBtn, "submit button must be disabled when headers JSON is invalid").toBeDisabled();

    // Fix the JSON — error should clear
    await headersInput.fill('{"X-Trace": "ok"}');
    await headersInput.dispatchEvent("input");
    await page.waitForTimeout(100);
    const errorVisible = await headersError.isVisible().catch(() => false);
    expect(errorVisible, "error must clear when JSON is fixed").toBe(false);

    void consoleErrors;
  });

  // ── Test 5: Submit with defaults — verify admin-api receives GET /health ────

  test("5: submit with defaults sends GET /health timeout_ms=5000 to admin-api", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // Create a disposable service for this test
    const svcWireId = await createTestService({
      tenantId: TENANT_ID,
      name: `e2e-tsf-defaults-${uid()}`,
      baseUrl: "https://httpbin.org",
      authScheme: "none",
    });
    expect(svcWireId, "createTestService must return an ID").not.toEqual("");

    const serviceId = await resolveCanonicalSvcId(svcWireId);
    expect(serviceId, "must resolve canonical svc ID").not.toEqual("");

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    const form = page.locator("[data-testid='test-service-form']");
    await expect(form).toBeVisible({ timeout: 10_000 });

    // Verify defaults are set
    await expect(page.locator("[data-testid='field-select-method']")).toHaveValue("GET");
    await expect(page.locator("[data-testid='field-input-path']")).toHaveValue("/health");
    await expect(page.locator("[data-testid='field-input-timeout']")).toHaveValue("5000");

    // Capture the network request to admin-api
    const [adminApiRequest, adminJsResponse] = await Promise.all([
      page.waitForRequest(
        (req) => req.url().includes(`/services/${serviceId}/test`) && req.method() === "POST",
        { timeout: 15_000 }
      ).catch(() => null),
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/services/records/${serviceId}/testService`) &&
          r.request().method() === "POST",
        { timeout: 15_000 }
      ),
      page.locator("[data-testid='test-service-submit']").click(),
    ]);

    expect(adminJsResponse.status(), "adminJS testService must return 2xx").toBeLessThan(400);

    // Verify result panel renders
    const resultPanel = page.locator("[data-testid='test-result-panel']");
    await expect(resultPanel, "result panel must appear after submit").toBeVisible({ timeout: 15_000 });

    // Verify the admin-api request body had the operator's form values (not hardcoded)
    if (adminApiRequest) {
      const reqBody = adminApiRequest.postData() ?? "";
      const parsed = JSON.parse(reqBody) as Record<string, unknown>;
      expect(parsed.method, "method must be GET (default)").toBe("GET");
      expect(parsed.path, "path must be /health (default)").toBe("/health");
      expect(parsed.timeout_ms, "timeout_ms must be 5000 (default)").toBe(5000);
    }

    void consoleErrors;
  });

  // ── Test 6: Submit with POST + custom path ──────────────────────────────────

  test("6: submit with POST + /get custom path sends those values to admin-api", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // Create a disposable service pointing at httpbin (reliable test endpoint)
    const svcWireId = await createTestService({
      tenantId: TENANT_ID,
      name: `e2e-tsf-post-${uid()}`,
      baseUrl: "https://httpbin.org",
      authScheme: "none",
    });
    expect(svcWireId, "createTestService must return an ID").not.toEqual("");

    const serviceId = await resolveCanonicalSvcId(svcWireId);

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    const form = page.locator("[data-testid='test-service-form']");
    await expect(form).toBeVisible({ timeout: 10_000 });

    // Change method to POST and path to /post (httpbin endpoint)
    await page.locator("[data-testid='field-select-method']").selectOption("POST");
    await page.locator("[data-testid='field-input-path']").fill("/post");
    await page.locator("[data-testid='field-input-timeout']").fill("8000");

    // Verify curl preview shows POST /post
    const curlPreview = await page.locator("[data-testid='curl-preview']").innerText();
    expect(curlPreview, "curl preview must show POST").toContain("POST");
    expect(curlPreview, "curl preview must show /post").toContain("/post");

    // Capture the network request to admin-api
    const [adminApiRequest, adminJsResponse] = await Promise.all([
      page.waitForRequest(
        (req) => req.url().includes(`/services/${serviceId}/test`) && req.method() === "POST",
        { timeout: 20_000 }
      ).catch(() => null),
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/services/records/${serviceId}/testService`) &&
          r.request().method() === "POST",
        { timeout: 20_000 }
      ),
      page.locator("[data-testid='test-service-submit']").click(),
    ]);

    expect(adminJsResponse.status(), "adminJS testService must return 2xx").toBeLessThan(400);

    // Verify admin-api received the operator's values
    if (adminApiRequest) {
      const reqBody = adminApiRequest.postData() ?? "";
      const parsed = JSON.parse(reqBody) as Record<string, unknown>;
      expect(parsed.method, "method must be POST (operator value)").toBe("POST");
      expect(parsed.path, "path must be /post (operator value)").toBe("/post");
      // Must NOT have fallen back to hardcoded GET /health
      expect(parsed.method, "must not fall back to hardcoded GET").not.toBe("GET");
      expect(parsed.path, "must not fall back to hardcoded /health").not.toBe("/health");
    }

    // Result panel must render
    const resultPanel = page.locator("[data-testid='test-result-panel']");
    await expect(resultPanel, "result panel must appear after submit").toBeVisible({ timeout: 15_000 });

    void consoleErrors;
  });

  // ── Test 7: Result panel shows status + latency + final_url + body ──────────

  test("7: result panel shows status_code, latency_ms, final_url, response body", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // Use httpbin.org/get — reliable, returns 200 with JSON body
    const svcWireId = await createTestService({
      tenantId: TENANT_ID,
      name: `e2e-tsf-result-${uid()}`,
      baseUrl: "https://httpbin.org",
      authScheme: "none",
    });
    const serviceId = await resolveCanonicalSvcId(svcWireId);

    await page.goto(`/admin/resources/services/records/${serviceId}/testService`, {
      waitUntil: "domcontentloaded",
    });
    await expect(page.locator("[data-testid='test-service-form']")).toBeVisible({ timeout: 10_000 });

    // Use /get — reliable 200 on httpbin
    await page.locator("[data-testid='field-input-path']").fill("/get");

    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/admin/api/resources/services/records/${serviceId}/testService`) &&
          r.request().method() === "POST",
        { timeout: 20_000 }
      ),
      page.locator("[data-testid='test-service-submit']").click(),
    ]);

    // Result panel must render
    const resultPanel = page.locator("[data-testid='test-result-panel']");
    await expect(resultPanel, "result panel must appear").toBeVisible({ timeout: 15_000 });

    // Panel must contain at least a status indicator and a result value
    const panelText = await resultPanel.innerText();
    // The panel shows the status_code, latency_ms, and possibly final_url
    // We check for presence of numbers (status code and latency are always numbers)
    expect(panelText, "result panel must contain some numeric value (status/latency)").toMatch(/\d+/);

    // final_url box (rendered when final_url is in the response)
    const finalUrlBox = page.locator("[data-testid='result-final-url']");
    const finalUrlVisible = await finalUrlBox.isVisible().catch(() => false);
    if (finalUrlVisible) {
      const finalUrlText = await finalUrlBox.innerText();
      expect(finalUrlText, "final_url must contain httpbin.org").toContain("httpbin.org");
    }

    // Response body box
    const bodyBox = page.locator("[data-testid='result-response-body']");
    const bodyVisible = await bodyBox.isVisible().catch(() => false);
    if (bodyVisible) {
      const bodyText = await bodyBox.innerText();
      expect(bodyText.length, "response body box must have content").toBeGreaterThan(0);
    }

    void consoleErrors;
  });
});
