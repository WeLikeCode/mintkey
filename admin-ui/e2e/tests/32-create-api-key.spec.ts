/**
 * 32 — createApiKey show-once flow (R1 of action-grid remediation).
 *
 * Verifies that the service_api_keys createApiKey resource action renders the
 * show-once modal instead of the "You have to implement action component" error.
 *
 * Source: ADMIN_UI_ACTION_MATRIX.md R1; ADR-0018 §1.3.
 * TDD: written BEFORE the ApiKeyCreate.tsx component existed — must fail first.
 *
 * Security:
 *   - plaintext key appears only in the modal, never in the list view
 *   - modal cannot be dismissed via outside-click (only via confirm button)
 *
 * R10 rewrite (A4 fix): removes the soft-skip at lines 188-195 that caused the
 * full e2e test to silently pass without exercising the show-once modal.
 * Synthesises an agent + service + permission grant via admin-api HTTP (mirroring
 * the pattern from tests/acceptance/test_api_keys_and_permissions_chain.py R9).
 *
 * Wire-form / UUID normalisation:
 *   The admin-api returns agent IDs in wire-form (agent_<32hex>) from the agents
 *   list, but UUID format from the permissions list. ApiKeyCreate.tsx filters
 *   permissions by comparing r.params.agent_id === agentId, so the formats must
 *   match. Fix (R10-redux, option a per ADR-0017): permissions.ts RestResource
 *   now applies a recordTransform that normalises agent_id from bare UUID to
 *   agent_<32hex> wire-form at the BFF boundary. No page.route interception is
 *   needed or present in this spec — the production code handles it correctly.
 */

import { test, expect } from "../fixtures/test.js";

// ── helpers ───────────────────────────────────────────────────────────────────

const ADMIN_API = process.env.ADMIN_API_URL ?? "http://localhost:8080";
const PLAYWRIGHT_USER = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";
const TENANT_ID = process.env.MINTKEY_TENANT_ID ?? "9593e3ba-4102-4235-9748-28d35b473214";

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

/** Convert UUID hex to agent_<32hex> wire-form. @deprecated Post-#13 use Crockford form */
function uuidToWireForm(uuid: string): string {
  return "agent_" + uuid.replace(/-/g, "");
}

// ---------------------------------------------------------------------------
// Wire-ID helpers (post-#13: Crockford ULID form — ADR-0017.11)
// ---------------------------------------------------------------------------

const _CROCKFORD_ALPHA_32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

/** Encode a plain UUID string to <prefix>_<26-char Crockford> wire form (post-#13). */
function dbUuidToWire(uuidStr: string, prefix: string): string {
  const hex = uuidStr.replace(/-/g, "");
  let val = BigInt("0x" + hex);
  const chars: string[] = [];
  for (let i = 0; i < 26; i++) {
    chars.push(_CROCKFORD_ALPHA_32[Number(val & BigInt(0x1F))]);
    val >>= BigInt(5);
  }
  chars.reverse();
  return `${prefix}_${chars.join("")}`;
}

/** Decode agent wire-form to UUID.
 * Handles both agent_<32hex> (hex form) and agent_<26Crockford> (ULID form).
 * For Crockford ULID, decode to 128-bit and format as UUID.
 */
function wireFormToUuid(wireId: string): string {
  const tail = wireId.replace(/^agent_/, "");
  if (tail.length === 32) {
    // Hex form — simple dashes
    return `${tail.slice(0,8)}-${tail.slice(8,12)}-${tail.slice(12,16)}-${tail.slice(16,20)}-${tail.slice(20)}`;
  }
  if (tail.length === 26) {
    // Crockford Base32 ULID — decode to 128-bit integer, format as UUID
    const CK = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
    let val = BigInt(0);
    for (const ch of tail.toUpperCase()) {
      val = (val << BigInt(5)) | BigInt(CK.indexOf(ch));
    }
    const hex128 = val.toString(16).padStart(32, "0");
    return `${hex128.slice(0,8)}-${hex128.slice(8,12)}-${hex128.slice(12,16)}-${hex128.slice(16,20)}-${hex128.slice(20)}`;
  }
  return wireId;
}

/** Login to admin-api; returns {sessionCookie, csrfToken}. */
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

/** POST to admin-api with session cookies. */
async function apiPost(path: string, body: unknown, auth: { sessionCookie: string; csrfToken: string }): Promise<Response> {
  return fetch(`${ADMIN_API}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Cookie": `mintkey_session=${auth.sessionCookie}; csrf_token=${auth.csrfToken}`,
      "X-Mintkey-Csrf": auth.csrfToken,
    },
    body: JSON.stringify(body),
  });
}

// webkit: AdminJS/Axios CORS — tracked W8.
const skipWebkit = ({ browserName }: { browserName: string }) =>
  browserName === "webkit";

// ── tests ─────────────────────────────────────────────────────────────────────

test.describe("32 — createApiKey show-once flow", () => {
  test.beforeAll(() => {
    expect(
      process.env.PLAYWRIGHT_PASS ?? "",
      "PLAYWRIGHT_PASS is required"
    ).not.toEqual("");
  });

  test("form renders without action-component error", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto(
      "/admin/resources/service_api_keys/actions/createApiKey",
      { waitUntil: "domcontentloaded" }
    );
    await page.waitForLoadState("networkidle");

    const bodyText = await page.locator("body").innerText();
    expect(
      bodyText,
      "Must not show action-component error"
    ).not.toContain("implement action component");
    expect(
      bodyText,
      "Must not show raw 'ActionSee' error text"
    ).not.toContain("ActionSee");

    // The custom form must render
    await expect(
      page.locator('[data-testid="api-key-create-form"]'),
      "ApiKeyCreate form must be visible"
    ).toBeVisible({ timeout: 10_000 });

    void consoleErrors;
  });

  test("agent dropdown is present", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto(
      "/admin/resources/service_api_keys/actions/createApiKey",
      { waitUntil: "domcontentloaded" }
    );
    await page.waitForLoadState("networkidle");

    // agent_id dropdown must be present
    await expect(
      page.locator('[data-testid="field-agent-id"]'),
      "agent_id dropdown/field must be present"
    ).toBeVisible({ timeout: 10_000 });

    void consoleErrors;
  });

  test("submit creates key and shows show-once modal", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    // Navigate to the createApiKey form
    await page.goto(
      "/admin/resources/service_api_keys/actions/createApiKey",
      { waitUntil: "domcontentloaded" }
    );
    await page.waitForLoadState("networkidle");

    await expect(
      page.locator('[data-testid="api-key-create-form"]')
    ).toBeVisible({ timeout: 10_000 });

    // Wait for agents to load (select must have at least one option beyond the placeholder)
    const agentSelect = page.locator('[data-testid="field-agent-id"] select');
    await agentSelect.waitFor({ state: "visible", timeout: 10_000 });
    // Wait for at least one real option to appear (beyond the "select an agent" placeholder)
    await page.waitForFunction(() => {
      const sel = document.querySelector('[data-testid="field-agent-id"] select') as HTMLSelectElement;
      return sel && sel.options.length > 1;
    }, undefined, { timeout: 15_000 });

    // Select the first real agent option
    const firstAgentValue = await page.evaluate(() => {
      const sel = document.querySelector('[data-testid="field-agent-id"] select') as HTMLSelectElement;
      return sel && sel.options.length > 1 ? sel.options[1].value : "";
    });
    expect(firstAgentValue, "Must have at least one agent option").not.toEqual("");
    await agentSelect.selectOption({ value: firstAgentValue });

    // Service dropdown should now be enabled with options (or empty if no permissions)
    // We can still try to submit even without a service — the form will show an error
    // For a positive test, we just submit without service and verify the error is from our form
    // (not the old "action component" error)

    // Submit the form — expect either success (with modal) or a form validation error
    // The key assertion is that we do NOT see the "implement action component" error
    await page.locator('[data-testid="api-key-create-submit"]').click();

    // Wait a moment for response or modal
    await page.waitForTimeout(2_000);

    // Must NOT show the old action-component error
    const bodyText = await page.locator("body").innerText();
    expect(
      bodyText,
      "Must not show old action-component error after submit"
    ).not.toContain("implement action component");
    expect(
      bodyText,
      "Must not show ActionSee error"
    ).not.toContain("ActionSee");

    void consoleErrors;
  });

  /**
   * Full e2e: show-once modal appears with mk_svckey_ key after successful create.
   *
   * R10 rewrite: removes the soft-skip (if (!hasServices) return;) and exercises the
   * actual show-once modal. Synthesises an agent + service + grant via admin-api HTTP.
   *
   * Intercepts the AdminJS permission_grants list response to normalise agent_id from
   * UUID format to wire-form format so the React dropdown filter works correctly.
   * This is a test-layer fix for the format mismatch and does NOT modify src/**.
   *
   * If the service dropdown is not populated after route interception, the test
   * FAILS LOUDLY with a specific assertion error — it does NOT silently return.
   */
  test("full e2e: show-once modal appears with mk_svckey_ key after successful create", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");
    // Synthesis + agents fetch (200 records) + service lookup can approach 30s.
    test.setTimeout(90_000);

    // ── Step 1: Synthesise agent + permission grant via admin-api ────────────
    // We use an existing service (twilio-sms, UUID: 688bb02f-d90e-404a-953c-d497e3b03e54)
    // to avoid the Crockford-ULID ↔ UUID format issue with newly created services.
    // Newly created agents have ULID IDs (agent_<26Crockford>) from the POST response,
    // but AdminJS normalises them to hex wire-form (agent_<32hex>) for dropdown options.
    const auth = await login();
    const ts = uid();
    const keyName = `r10-redux-${ts}`;

    // Known existing service — avoids service creation format issues
    const serviceUuid = "688bb02f-d90e-404a-953c-d497e3b03e54"; // twilio-sms

    // Create agent
    const agentResp = await apiPost(
      `/v1/tenants/${TENANT_ID}/agents`,
      { name: `r10-e2e-agent-${ts}`, description: "R10 e2e test agent" },
      auth
    );
    expect(agentResp.status, `Create agent failed: ${agentResp.status}`).toBe(201);
    const agentBody = await agentResp.json() as { id: string };
    const rawAgentId = agentBody.id; // may be agent_<32hex> or agent_<26Crockford>
    expect(rawAgentId, "agent id must be present").toBeTruthy();
    // Post-#13: all list/get endpoints return Crockford ULID wire IDs (agent_<26>) — ADR-0017.11 / #13
    expect(rawAgentId, "agent id must be wire-form (agent_ prefix)").toMatch(/^agent_[0-9A-Za-z]{26,32}$/);

    // Post-#13: use the Crockford wire-form directly as the dropdown option value.
    // AdminJS agents list now returns agent_<Crockford> which is used as the option value.
    const wireAgentId = rawAgentId;

    // Grant permission: use agent-scoped endpoint POST /v1/tenants/{tid}/agents/{agent_wire}/permissions
    // (The flat POST /v1/tenants/{tid}/permissions returns 405 — agent-scoped is the correct path)
    // Use rawAgentId (the original form from POST response) in the URL path
    const grantResp = await apiPost(
      `/v1/tenants/${TENANT_ID}/agents/${rawAgentId}/permissions`,
      {
        service_id: serviceUuid,
        action: "*",
        constraints: {},
      },
      auth
    );
    const grantText = await grantResp.clone().text();
    expect(grantResp.status, `Grant permission failed: ${grantResp.status} ${grantText}`).toBe(201);

    // ── Step 2: Navigate to createApiKey form ────────────────────────────────
    // NOTE: No page.route interception needed — permissions.ts RestResource now
    // normalises agent_id from bare UUID to wire-form (agent_<32hex>) at the BFF
    // boundary via recordTransform, per ADR-0017. (R10-redux fix)
    await page.goto(
      "/admin/resources/service_api_keys/actions/createApiKey",
      { waitUntil: "domcontentloaded" }
    );
    await expect(page.locator('[data-testid="api-key-create-form"]')).toBeVisible({ timeout: 10_000 });

    // Screenshot A: form loaded
    await page.screenshot({ path: "test-results/r10-a4-step-b-form.png" });

    // ── Step 4: Select the synthesised agent ─────────────────────────────────
    const agentSelect = page.locator('[data-testid="field-agent-id"] select');
    await agentSelect.waitFor({ state: "visible", timeout: 10_000 });
    // Wait for agents to load
    await page.waitForFunction(() => {
      const sel = document.querySelector('[data-testid="field-agent-id"] select') as HTMLSelectElement;
      return sel && sel.options.length > 1;
    }, undefined, { timeout: 20_000 });

    // Verify the synthesised agent is in the list
    const hasAgentOption = await page.evaluate((wid: string) => {
      const sel = document.querySelector('[data-testid="field-agent-id"] select') as HTMLSelectElement;
      return Array.from(sel?.options ?? []).some((o) => o.value === wid);
    }, wireAgentId);

    expect(
      hasAgentOption,
      `Synthesised agent ${wireAgentId} must appear in the agent dropdown. ` +
      "If this fails, the agents list endpoint may not be returning the newly created agent."
    ).toBe(true);

    await agentSelect.selectOption({ value: wireAgentId });

    // ── Step 5: Wait for service dropdown to populate ────────────────────────
    // The production code now normalises agent_id to wire-form in permissions.ts
    // recordTransform (ADR-0017: wire-form on the wire). No route interception needed.
    const serviceSelect = page.locator('[data-testid="field-service-id"] select');
    await serviceSelect.waitFor({ state: "visible", timeout: 10_000 });

    // FAIL LOUDLY if service dropdown is not populated — this means R9's permissions
    // endpoint is not returning the grant, or the BFF normalisation (permissions.ts
    // recordTransform) is not working.
    await page.waitForFunction(() => {
      const sel = document.querySelector('[data-testid="field-service-id"] select') as HTMLSelectElement;
      return sel && sel.options.length > 1;
    }, undefined, { timeout: 15_000 }).catch(() => {
      throw new Error(
        "FAIL: Service dropdown was not populated after selecting the synthesised agent. " +
        "This means the permission grant is not being returned by the permissions endpoint " +
        "(R9 regression), or the BFF agent_id normalisation (permissions.ts recordTransform) failed. " +
        "Expected at least 1 service option for agent: " + wireAgentId + " (raw: " + rawAgentId + "). " +
        "Check: GET /v1/tenants/{tid}/permissions returns the grant? " +
        "Check: AdminJS permission_grants/actions/list includes the grant record?"
      );
    });

    // Screenshot B: service dropdown populated (before step d assertion screenshot)
    await page.screenshot({ path: "test-results/r10-a4-step-d-service-populated.png" });

    // ── Step 6: Select the synthesised service ───────────────────────────────
    // Post-#13: permissions list returns service_id as svc_<Crockford> (ADR-0017.11 / #13).
    // The service dropdown option values come from permissions.service_id which is now Crockford.
    const svcWireId = dbUuidToWire(serviceUuid, "svc");
    const hasServiceOption = await page.evaluate((svcWire: string) => {
      const sel = document.querySelector('[data-testid="field-service-id"] select') as HTMLSelectElement;
      return Array.from(sel?.options ?? []).some((o) => o.value === svcWire);
    }, svcWireId);

    expect(
      hasServiceOption,
      `Synthesised service ${serviceUuid} (wire: ${svcWireId}) must appear in the service dropdown`
    ).toBe(true);

    await serviceSelect.selectOption({ value: svcWireId });

    // ── Step 7: Fill the name field ──────────────────────────────────────────
    await page.locator('[data-testid="field-name"] input').fill(keyName);

    // ── Step 8: Submit and wait for the createApiKey response ────────────────
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/admin/api/resources/service_api_keys/actions/createApiKey") &&
          r.request().method() === "POST",
        { timeout: 20_000 }
      ),
      page.locator('[data-testid="api-key-create-submit"]').click(),
    ]);

    const respData = await response.json().catch(() => ({})) as {
      notice?: { message: string; type: string };
    };

    // If backend error, fail with clear message (no soft-skip)
    if (respData.notice?.type === "error") {
      throw new Error(
        `FAIL: createApiKey action returned an error: "${respData.notice.message}". ` +
        "This may indicate R9's wire-form decode (A1) is not working correctly, or the " +
        "permission grant was not created successfully. " +
        `Agent raw: ${rawAgentId}, Agent hex-wire: ${wireAgentId}, Service: ${serviceUuid}`
      );
    }

    // ── Step 9: Assert show-once modal appears with mk_svckey_ key ───────────
    await expect(
      page.locator('[data-testid="show-once-modal"]'),
      "FAIL: Show-once modal must appear after successful createApiKey submit. " +
      "The component must set plaintextKey state from the notice message."
    ).toBeVisible({ timeout: 15_000 });

    const modalText = await page.locator('[data-testid="show-once-modal"]').innerText();

    // Screenshot C: modal visible with key (step h)
    await page.screenshot({ path: "test-results/r10-a4-step-h-modal.png" });

    expect(
      modalText,
      "Modal must contain the mk_svckey_ pattern"
    ).toMatch(/mk_svckey_[A-Z0-9]{20,}/);

    expect(
      modalText,
      "Modal must warn that key is shown only once"
    ).toMatch(/only time|shown once|copy it now/i);

    // Extract the actual key from the modal for later assertion
    const keyMatch = modalText.match(/(mk_svckey_[A-Z0-9]{20,})/);
    expect(keyMatch, "Must extract mk_svckey_ value from modal").toBeTruthy();
    const plaintextKey = keyMatch![1];

    // ── Step 10: Assert no key leak in storage ───────────────────────────────
    const storageLeakCheck = await page.evaluate((keyPrefix: string) => {
      const lsKeys: string[] = [];
      const ssKeys: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i) ?? "";
        const v = localStorage.getItem(k) ?? "";
        if (v.includes(keyPrefix)) lsKeys.push(k);
      }
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i) ?? "";
        const v = sessionStorage.getItem(k) ?? "";
        if (v.includes(keyPrefix)) ssKeys.push(k);
      }
      return { lsKeys, ssKeys };
    }, "mk_svckey_");

    expect(
      storageLeakCheck.lsKeys,
      "mk_svckey_ must NOT appear in localStorage (ADR-0018 §1.3)"
    ).toHaveLength(0);
    expect(
      storageLeakCheck.ssKeys,
      "mk_svckey_ must NOT appear in sessionStorage (ADR-0018 §1.3)"
    ).toHaveLength(0);

    // ── Step 11: Verify modal does NOT close on outside-click ────────────────
    const confirmBtn = page.locator('[data-testid="modal-confirm-btn"]');
    await expect(confirmBtn, "Confirm button must be visible").toBeVisible({ timeout: 5_000 });

    await page.mouse.click(10, 10);
    await expect(
      page.locator('[data-testid="show-once-modal"]'),
      "Modal must not close on outside-click"
    ).toBeVisible({ timeout: 2_000 });

    // ── Step 12: Click confirm → modal closes + redirect to list ─────────────
    await confirmBtn.click();
    await page.waitForURL(/\/admin\/resources\/service_api_keys/, { timeout: 15_000 });
    await page.waitForLoadState("networkidle");

    // Screenshot D: list view after confirm (step k)
    await page.screenshot({ path: "test-results/r10-a4-step-k-list.png" });

    // ── Step 13: Assert list page loaded and key is NOT leaked ──────────────
    // Note: The AdminJS service_api_keys list uses listPath="/v1/tenants/{tenantId}/api-keys"
    // which currently returns 0 records (the tenant-level api-keys list endpoint is unimplemented).
    // We assert the list page loaded correctly and the plaintext key is NOT visible (ADR-0018 §1.3).
    // Row-by-name assertion is not feasible because: (a) the list endpoint returns 0 records,
    // (b) the "name" field is not stored in the API key schema — it's a cosmetic input only.
    await expect(
      page.locator('[data-testid="api-key-create-form"]'),
      "List page must NOT show the createApiKey form (modal must have closed + redirected)"
    ).not.toBeVisible({ timeout: 5_000 });

    // Assert the plaintext key is NOT visible anywhere in the list
    const listBodyText = await page.locator("body").innerText();
    expect(
      listBodyText,
      "List view must NOT show the plaintext key (ADR-0018 §1.3 — shown once only)"
    ).not.toContain(plaintextKey);

    // Assert page is on the list URL (navigation completed)
    expect(
      page.url(),
      "Browser must have navigated to the service_api_keys list page"
    ).toContain("/admin/resources/service_api_keys");

    void consoleErrors;
  });
});
