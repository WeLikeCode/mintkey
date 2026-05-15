/**
 * 39 — UX-CLARITY chunk D: field descriptions render on forms.
 *
 * Asserts that the `action`, `constraints`, and `allowed_actions` description
 * strings are present in the AdminJS Redux metadata for permission_grants and
 * service_api_keys resources respectively.  Also verifies:
 *   - The `action` field is free-text (accepts `<verb>:<resource>` without errors).
 *   - A bad `constraints` key ("{\"foo\": 1}") surfaces a visible 422 / error notice
 *     from the backend (does NOT silently succeed).
 *   - The PermissionsIntro and ApiKeysIntro banners include the expanded guidance text.
 *
 * Implementation note:
 *   AdminJS v7 renders property `description` as a tooltip (not as inline visible
 *   text). The description value lives in window.REDUX_STATE (the AdminJS Redux
 *   store) which is embedded as a script in the page. We read it via page.evaluate()
 *   to assert the value without relying on rendered DOM text.
 *
 * Source: admin-ui-ux-uplift chunk D (UX-CLARITY); Opus architectural decision
 *         to keep action / allowed_actions as free-text (not static dropdowns).
 */

import { test, expect } from "../fixtures/test.js";

// webkit: AdminJS/Axios CORS — tracked W8
const skipWebkit = ({ browserName }: { browserName: string }) =>
  browserName === "webkit";

// ── helpers ──────────────────────────────────────────────────────────────────

type ReduxState = {
  resources: Array<{
    id: string;
    properties: Record<string, { description?: string }>;
  }>;
};

/**
 * Read window.REDUX_STATE from the browser JS context.
 * AdminJS sets this global before React mounts, so it is available immediately
 * after the page parses its inline <script> block.
 */
async function getReduxState(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
): Promise<ReduxState | null> {
  return page.evaluate(() => {
    const w = window as unknown as Record<string, unknown>;
    const rs = w["REDUX_STATE"];
    return rs ? (rs as ReduxState) : null;
  });
}

/**
 * Find a property's description from the AdminJS Redux state.
 */
function getPropertyDescription(
  state: ReduxState,
  resourceId: string,
  propertyPath: string,
): string | null {
  const resource = state.resources.find((r) => r.id === resourceId);
  if (!resource) return null;
  return resource.properties[propertyPath]?.description ?? null;
}

/** Return visible innerText of the page body. */
async function bodyText(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
): Promise<string> {
  return (await page.locator("body").innerText().catch(() => "")) ?? "";
}

// ── Permissions new form ──────────────────────────────────────────────────────

test.describe("39 — UX-CLARITY: Permissions new form — field descriptions", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("action field description is in Redux state — mentions `call` and <verb>:<resource>", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle");

    const state = await getReduxState(page);
    expect(state, "window.REDUX_STATE must be present on the page").toBeTruthy();
    if (!state) return;

    const desc = getPropertyDescription(state, "permission_grants", "action");
    expect(desc, "action property must have a non-empty description").toBeTruthy();
    expect(desc!, "action description must mention `call`").toMatch(/call/);
    expect(desc!, "action description must mention <verb>:<resource>").toMatch(/<verb>:<resource>/);
    expect(
      desc!,
      "action description must include a concrete example",
    ).toMatch(/read:contacts|write:invoices|delete:invoices/);

    void consoleErrors;
  });

  test("constraints field description is in Redux state — lists allowed keys and 422", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle");

    const state = await getReduxState(page);
    expect(state, "window.REDUX_STATE must be present on the page").toBeTruthy();
    if (!state) return;

    const desc = getPropertyDescription(state, "permission_grants", "constraints");
    expect(desc, "constraints property must have a non-empty description").toBeTruthy();
    expect(desc!, "constraints description must mention rate_limit").toContain("rate_limit");
    expect(desc!, "constraints description must mention time_window").toContain("time_window");
    expect(desc!, "constraints description must mention request_path_prefix").toContain("request_path_prefix");
    expect(desc!, "constraints description must mention source_ip_allowlist").toContain("source_ip_allowlist");
    expect(desc!, "constraints description must mention 422").toMatch(/422/);

    void consoleErrors;
  });

  test("action field is free-text — accepts <verb>:<resource> value without errors", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto("/admin/resources/permission_grants/actions/new", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    // The action field must be a plain text input, not a <select>
    const actionInput = page.getByLabel(/^action$/i);
    await expect(
      actionInput,
      "action field must be a visible free-text input",
    ).toBeVisible({ timeout: 10_000 });

    const tagName = await actionInput.evaluate((el) => el.tagName.toLowerCase());
    expect(tagName, "action field must be <input>, not <select>").not.toBe("select");

    // Type a <verb>:<resource> value — the input must accept it without constraint
    await actionInput.fill("read:contacts");
    const inputValue = await actionInput.inputValue();
    expect(
      inputValue,
      "action field must accept read:contacts (free-text)",
    ).toBe("read:contacts");

    void consoleErrors;
  });

  test("submitting unknown constraints key surfaces 422 error notice", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto("/admin/resources/permission_grants/actions/new", {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle");

    // Fill required fields with valid-looking values
    const agentIdField = page.getByLabel(/agent.?id/i);
    const serviceIdField = page.getByLabel(/service.?id/i);
    const actionField = page.getByLabel(/^action$/i);
    const constraintsField = page.getByLabel(/constraints/i);

    if ((await agentIdField.count()) > 0) await agentIdField.fill("agent_nonexistent");
    if ((await serviceIdField.count()) > 0) await serviceIdField.fill("svc_nonexistent");
    if ((await actionField.count()) > 0) await actionField.fill("read:contacts");
    if ((await constraintsField.count()) > 0) await constraintsField.fill('{"foo": 1}');

    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/admin/api/resources/permission_grants/actions/new") &&
          r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.getByRole("button", { name: /save|grant/i }).click(),
    ]);

    const respData = await resp.json().catch(() => ({}) as Record<string, unknown>) as Record<string, unknown>;
    const noticeMsg = ((respData.notice as { message?: string } | undefined)?.message) ?? "";
    const noticeType = ((respData.notice as { type?: string } | undefined)?.type) ?? "";
    const body = await bodyText(page);

    // We expect: either a 422 backend error, or a client-side validation error notice.
    const hasErrorSignal =
      noticeType === "error" ||
      /422|unknown key|unrecognized|not allowed|invalid/i.test(noticeMsg) ||
      /422|unknown key|unrecognized|not allowed/i.test(body);

    expect(
      hasErrorSignal,
      `Submitting {"foo": 1} for constraints must surface an error. ` +
      `Got noticeType="${noticeType}", noticeMsg="${noticeMsg}"`,
    ).toBe(true);

    void consoleErrors;
  });
});

// ── API Keys createApiKey form ────────────────────────────────────────────────

test.describe("39 — UX-CLARITY: API Keys — allowed_actions description", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("allowed_actions description is in Redux state — mentions comma-separated, subset, 422", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle");

    const state = await getReduxState(page);
    expect(state, "window.REDUX_STATE must be present on the page").toBeTruthy();
    if (!state) return;

    const desc = getPropertyDescription(state, "service_api_keys", "allowed_actions");
    expect(desc, "allowed_actions property must have a non-empty description").toBeTruthy();
    expect(
      desc!,
      "allowed_actions description must mention comma-separated",
    ).toMatch(/[Cc]omma.?separated/);
    expect(desc!, "allowed_actions description must mention subset").toMatch(/subset/);
    expect(desc!, "allowed_actions description must mention 422").toMatch(/422/);
    expect(desc!, "allowed_actions description must mention `call`").toMatch(/call/);

    void consoleErrors;
  });
});

// ── Intro banners ─────────────────────────────────────────────────────────────

test.describe("39 — UX-CLARITY: Intro banner expansions", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("PermissionsIntro includes action format guidance", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/permission_grants", { waitUntil: "domcontentloaded" });
    await page
      .locator('[data-testid="resource-intro-banner"], table, :text("No records")')
      .first()
      .waitFor({ state: "visible", timeout: 25_000 })
      .catch(() => {});

    const body = await bodyText(page);
    expect(
      body,
      "Permissions intro must contain action format guidance (call or <verb>:<resource>)",
    ).toMatch(/call.*unrestricted|verb.*resource|action.*format|action.*scope/i);

    void consoleErrors;
  });

  test("ApiKeysIntro includes allowed_actions guidance", async ({
    page,
    consoleErrors,
  }) => {
    await page.goto("/admin/resources/service_api_keys", { waitUntil: "domcontentloaded" });
    await page
      .locator('[data-testid="resource-intro-banner"], table, :text("No records")')
      .first()
      .waitFor({ state: "visible", timeout: 25_000 })
      .catch(() => {});

    const body = await bodyText(page);
    expect(
      body,
      "ApiKeys intro must contain allowed_actions guidance",
    ).toMatch(/allowed_actions|subset.*grants|grants.*subset/i);

    void consoleErrors;
  });
});
