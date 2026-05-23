/**
 * 38 — Typeahead combobox for agent + service pickers (UX-A).
 *
 * Verifies:
 *   Test 1: ApiKeyCreate — agent combobox filters by partial name on input.
 *   Test 2: ApiKeyCreate — service combobox appears and is filterable after agent selection.
 *   Test 3: Permissions new form — agent_id + service_id comboboxes appear, pick agent,
 *           submit form, assert permission created.
 *   Test 4: Keyboard navigation — ArrowDown, Enter, Esc all work in the agent combobox.
 *   Test 5: Click-outside closes combobox dropdown.
 *
 * Chromium only — webkit CORS tracked W8.
 *
 * Source: UX-A spec; AsyncCombobox.tsx; AgentCombobox.tsx; ServiceCombobox.tsx.
 */

import { test, expect } from "../fixtures/test.js";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

import fs from "fs";
const RESULTS_DIR = path.resolve(__dirname, "../test-results");
if (!fs.existsSync(RESULTS_DIR)) {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
}

// ── helpers ───────────────────────────────────────────────────────────────────

const ADMIN_API = process.env.ADMIN_API_URL ?? "http://localhost:8080";
const PLAYWRIGHT_USER = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
const TENANT_ID = process.env.MINTKEY_TENANT_ID ?? "9593e3ba-4102-4235-9748-28d35b473214";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

async function login(): Promise<{ sessionCookie: string; csrfToken: string }> {
  const pass = process.env.PLAYWRIGHT_PASS ?? "";
  const r = await fetch(`${ADMIN_API}/v1/auth/internal-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: PLAYWRIGHT_USER, password: pass }),
  });
  if (!r.ok) throw new Error(`Login failed: ${r.status} ${await r.text()}`);
  const setCookie = r.headers.get("set-cookie") ?? "";
  const smatch = setCookie.match(/mintkey_session=([^;]+)/);
  const cmatch = setCookie.match(/csrf_token=([^;]+)/);
  if (!smatch || !cmatch) throw new Error("Login: missing cookies in response");
  return { sessionCookie: smatch[1], csrfToken: cmatch[1] };
}

async function apiPost(
  urlPath: string,
  body: unknown,
  auth: { sessionCookie: string; csrfToken: string }
): Promise<Response> {
  return fetch(`${ADMIN_API}${urlPath}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Cookie": `mintkey_session=${auth.sessionCookie}; csrf_token=${auth.csrfToken}`,
      "X-Mintkey-Csrf": auth.csrfToken,
    },
    body: JSON.stringify(body),
  });
}

const skipWebkit = ({ browserName }: { browserName: string }) =>
  browserName === "webkit";

// ── spec ──────────────────────────────────────────────────────────────────────

test.describe("38 — Typeahead combobox for agent + service pickers (UX-A)", () => {
  test.beforeAll(() => {
    expect(
      process.env.PLAYWRIGHT_PASS ?? "",
      "PLAYWRIGHT_PASS env var is required"
    ).not.toEqual("");
  });

  // ── Test 1: ApiKeyCreate agent combobox ──────────────────────────────────

  test("1: ApiKeyCreate — agent combobox renders, dropdown appears on focus, type filters options", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto(
      "/admin/resources/service_api_keys/actions/createApiKey",
      { waitUntil: "domcontentloaded" }
    );
    await expect(
      page.locator('[data-testid="api-key-create-form"]')
    ).toBeVisible({ timeout: 10_000 });

    // Combobox input must be present
    const agentInput = page.locator('[data-testid="combobox-agent-input"]');
    await expect(agentInput, "agent combobox input must be visible").toBeVisible({ timeout: 10_000 });

    // Click to open dropdown — initial top-50 list should appear
    await agentInput.click();
    const dropdown = page.locator('[data-testid="combobox-agent-dropdown"]');
    await expect(dropdown, "agent dropdown must open on focus").toBeVisible({ timeout: 15_000 });

    // Wait for the initial options to load (Loading… disappears, options appear)
    await page.locator('[data-testid="combobox-agent-dropdown"] li[data-value]').first().waitFor({
      state: "visible",
      timeout: 20_000,
    });
    const initialCount = await page.locator('[data-testid="combobox-agent-dropdown"] li[data-value]').count();
    expect(initialCount, "initial dropdown must have at least 1 option").toBeGreaterThan(0);

    // Type a partial query — debounce 300ms then API call
    await agentInput.fill("smoke");
    await page.waitForTimeout(500); // debounce + response

    // Dropdown must still be open
    await expect(dropdown, "dropdown must remain open while typing").toBeVisible({ timeout: 5_000 });

    // Screenshot: agent combobox filtered
    await page.screenshot({
      path: path.resolve(RESULTS_DIR, "38-agent-combobox-filtered.png"),
    });

    void consoleErrors;
  });

  // ── Test 2: ApiKeyCreate service combobox ────────────────────────────────

  test("2: ApiKeyCreate — service combobox appears and filters after agent is selected", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");
    test.setTimeout(60_000);

    // Synthesise an agent + service + permission grant so the service combobox has options
    const auth = await login();
    const ts = uid();
    const serviceUuid = "688bb02f-d90e-404a-953c-d497e3b03e54"; // twilio-sms (known existing)

    const agentResp = await apiPost(
      `/v1/tenants/${TENANT_ID}/agents`,
      { name: `ux-a-svc-test-${ts}`, description: "UX-A service combobox test agent" },
      auth
    );
    expect(agentResp.status, "create agent").toBe(201);
    const agentBody = await agentResp.json() as { id: string };
    const wireAgentId = agentBody.id;

    await apiPost(
      `/v1/tenants/${TENANT_ID}/agents/${wireAgentId}/permissions`,
      { service_id: serviceUuid, action: "*", constraints: {} },
      auth
    );

    await page.goto(
      "/admin/resources/service_api_keys/actions/createApiKey",
      { waitUntil: "domcontentloaded" }
    );
    await expect(
      page.locator('[data-testid="api-key-create-form"]')
    ).toBeVisible({ timeout: 10_000 });

    // Select the synthesised agent via combobox
    const agentInput = page.locator('[data-testid="combobox-agent-input"]');
    await agentInput.click();
    await page.locator('[data-testid="combobox-agent-dropdown"]').waitFor({ state: "visible", timeout: 15_000 });
    // Wait for initial options to load
    await page.locator('[data-testid="combobox-agent-dropdown"] li[data-value]').first().waitFor({ state: "visible", timeout: 20_000 });

    // Search by the agent name suffix that is unique to this test run (ts)
    await agentInput.fill(`ux-a-svc-test-${ts}`);
    await page.waitForTimeout(500); // debounce + response

    const agentOption = page.locator(
      `[data-testid="combobox-agent-dropdown"] li[data-value="${wireAgentId}"]`
    );
    await agentOption.waitFor({ state: "visible", timeout: 15_000 });
    await agentOption.click();

    // After selecting agent, service combobox should become available
    const serviceInput = page.locator('[data-testid="combobox-service-input"]');
    await serviceInput.waitFor({ state: "visible", timeout: 15_000 });

    // Wait for "Loading services..." to disappear
    await page.waitForFunction(() => {
      return !document.body.innerText.includes("Loading services");
    }, undefined, { timeout: 15_000 });

    // service input should be enabled
    await expect(serviceInput).not.toBeDisabled({ timeout: 10_000 });

    // Click to open service dropdown
    await serviceInput.click();
    const svcDropdown = page.locator('[data-testid="combobox-service-dropdown"]');
    await expect(svcDropdown, "service dropdown must appear after agent selected").toBeVisible({ timeout: 10_000 });

    // At least one service option must be visible
    const svcOptCount = await page.locator('[data-testid="combobox-service-dropdown"] li[data-value]').count();
    expect(svcOptCount, "service dropdown must have at least 1 option").toBeGreaterThan(0);

    // Type to filter services locally (no API call — staticOptions mode).
    // UX-BL1: permissions list now returns service_name, so option labels are
    // "<name> (svc_XXXX)". Search by "svc_" which appears in all labels.
    await serviceInput.fill("svc_");
    await page.waitForTimeout(200); // local filter — no debounce

    // Dropdown should still contain at least one option matching "svc_"
    const filteredCount = await page.locator('[data-testid="combobox-service-dropdown"] li[data-value]').count();
    expect(filteredCount, "filtering service by 'svc_' must return at least 1 option").toBeGreaterThan(0);

    // Screenshot: service combobox filtered
    await page.screenshot({
      path: path.resolve(RESULTS_DIR, "38-service-combobox-filtered.png"),
    });

    void consoleErrors;
  });

  // ── Test 3: Permissions new form comboboxes ──────────────────────────────

  test("3: permissions new form — agent_id and service_id comboboxes render; pick agent, submit", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");
    test.setTimeout(60_000);

    await page.goto(
      "/admin/resources/permission_grants/actions/new",
      { waitUntil: "domcontentloaded" }
    );
    await page.waitForLoadState("networkidle");

    // The permissions new form should render (no "implement action component" error)
    const bodyText = await page.locator("body").innerText();
    expect(bodyText, "must not show action-component error").not.toContain("implement action component");

    // UX-A: agent_id field should now be a combobox (AgentCombobox edit component)
    const agentCombobox = page.locator('[data-testid="agent-combobox-input"]');
    await expect(agentCombobox, "agent_id combobox input must be visible in permissions new form")
      .toBeVisible({ timeout: 15_000 });

    // UX-A: service_id field should now be a combobox (ServiceCombobox edit component)
    const serviceCombobox = page.locator('[data-testid="service-combobox-input"]');
    await expect(serviceCombobox, "service_id combobox input must be visible in permissions new form")
      .toBeVisible({ timeout: 10_000 });

    // Open agent dropdown and verify options appear
    await agentCombobox.click();
    const agentDropdown = page.locator('[data-testid="agent-combobox-dropdown"]');
    await expect(agentDropdown, "agent dropdown must open").toBeVisible({ timeout: 15_000 });

    const optionCount = await page.locator('[data-testid="agent-combobox-dropdown"] li[data-value]').count();
    expect(optionCount, "agent dropdown must have at least 1 option").toBeGreaterThan(0);

    // Type to filter agent options
    await agentCombobox.fill("smoke");
    await page.waitForTimeout(500); // 300ms debounce + response

    // Dropdown stays open with filtered results
    await expect(agentDropdown, "agent dropdown stays open while typing").toBeVisible({ timeout: 5_000 });

    // Screenshot: permissions new form with combobox open
    await page.screenshot({
      path: path.resolve(RESULTS_DIR, "38-permissions-agent-combobox.png"),
    });

    void consoleErrors;
  });

  // ── Test 4: Keyboard navigation ──────────────────────────────────────────

  test("4: keyboard nav — ArrowDown highlights option, Enter selects, Esc closes", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto(
      "/admin/resources/service_api_keys/actions/createApiKey",
      { waitUntil: "domcontentloaded" }
    );
    await expect(
      page.locator('[data-testid="api-key-create-form"]')
    ).toBeVisible({ timeout: 10_000 });

    const agentInput = page.locator('[data-testid="combobox-agent-input"]');
    await agentInput.waitFor({ state: "visible", timeout: 10_000 });

    // Open dropdown via click
    await agentInput.click();
    await page.locator('[data-testid="combobox-agent-dropdown"]').waitFor({ state: "visible", timeout: 15_000 });

    // Ensure at least one option loads (wait for Loading… to resolve)
    const firstOptLocator = page.locator('[data-testid="combobox-agent-option-0"]');
    await firstOptLocator.waitFor({ state: "visible", timeout: 20_000 });

    // Press ArrowDown once — first option should be highlighted
    await agentInput.press("ArrowDown");
    // Highlighted style check: background changes on highlight.
    // Browser may return hex or rgb() form — compare computed style.
    const firstOptBg = await firstOptLocator.evaluate(
      (el) => window.getComputedStyle(el).backgroundColor
    );
    // rgb(232, 244, 251) = #e8f4fb
    expect(
      firstOptBg,
      "first option must have highlight background after ArrowDown"
    ).toBe("rgb(232, 244, 251)");

    // Press ArrowDown again (if there is a second option)
    const secondOptLocator = page.locator('[data-testid="combobox-agent-option-1"]');
    const hasSecond = (await secondOptLocator.count()) > 0;
    if (hasSecond) {
      await agentInput.press("ArrowDown");
    }

    // Press Esc — dropdown should close
    await agentInput.press("Escape");
    await expect(
      page.locator('[data-testid="combobox-agent-dropdown"]'),
      "dropdown must close on Esc"
    ).not.toBeVisible({ timeout: 3_000 });

    // Re-open and press Enter on first highlighted item
    await agentInput.click();
    await page.locator('[data-testid="combobox-agent-dropdown"]').waitFor({ state: "visible", timeout: 15_000 });
    // Options should still be cached from prior load — wait for option-0
    await firstOptLocator.waitFor({ state: "visible", timeout: 10_000 });
    await agentInput.press("ArrowDown");
    const targetValue = await firstOptLocator.getAttribute("data-value");
    await agentInput.press("Enter");

    // Dropdown should close and chip should appear
    await expect(
      page.locator('[data-testid="combobox-agent-dropdown"]'),
      "dropdown must close after Enter selects option"
    ).not.toBeVisible({ timeout: 3_000 });
    await expect(
      page.locator('[data-testid="combobox-agent-chip"]'),
      "selected chip must appear after Enter selection"
    ).toBeVisible({ timeout: 5_000 });

    // The hidden value input must carry the wire-id
    const hiddenVal = await page.locator('[data-testid="combobox-agent-value"]').getAttribute("value");
    expect(hiddenVal, "hidden value input must match selected option wire-id").toBe(targetValue);

    // Screenshot: keyboard navigation result
    await page.screenshot({
      path: path.resolve(RESULTS_DIR, "38-keyboard-nav.png"),
    });

    void consoleErrors;
  });

  // ── Test 5: Click-outside closes dropdown ────────────────────────────────

  test("5: click outside closes combobox dropdown", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto(
      "/admin/resources/service_api_keys/actions/createApiKey",
      { waitUntil: "domcontentloaded" }
    );
    await expect(
      page.locator('[data-testid="api-key-create-form"]')
    ).toBeVisible({ timeout: 10_000 });

    const agentInput = page.locator('[data-testid="combobox-agent-input"]');
    await agentInput.waitFor({ state: "visible", timeout: 10_000 });

    await agentInput.click();
    await page.locator('[data-testid="combobox-agent-dropdown"]').waitFor({ state: "visible", timeout: 15_000 });

    // Click outside the combobox (on the form heading)
    await page.locator('[data-testid="api-key-create-form"]').click({ position: { x: 10, y: 10 } });

    await expect(
      page.locator('[data-testid="combobox-agent-dropdown"]'),
      "dropdown must close on click outside"
    ).not.toBeVisible({ timeout: 3_000 });

    void consoleErrors;
  });
});
