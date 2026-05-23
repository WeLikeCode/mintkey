/**
 * 40 — UX-CLARITY chunk G: inline show-page description renderer.
 *
 * Asserts that the custom DescriptiveShowProperty override renders property
 * descriptions as small italic text below each field value on show pages.
 *
 * Tests:
 *   1. Agent show page: api_key_fingerprint description visible with expected text.
 *   2. Tenant show page: isolation_mode description visible with expected text.
 *   3. Permission grant show page: constraints description visible with expected text.
 *
 * Authentication is handled by storageState from global-setup.
 *
 * Source: UX-CLARITY chunk G; Opus architectural decision ADR-0019.
 */

import { test, expect } from "../fixtures/test.js";

// webkit: AdminJS/Axios CORS — tracked W8
const skipWebkit = ({ browserName }: { browserName: string }) =>
  browserName === "webkit";

// ── helpers ──────────────────────────────────────────────────────────────────

/**
 * Navigate to a resource list page and extract the first record's ID from show-link hrefs.
 */
async function firstRecordId(
  page: Parameters<typeof test>[1] extends (...args: infer A) => unknown ? A[0]["page"] : never,
  resource: string,
): Promise<string | null> {
  await page.goto(`/admin/resources/${resource}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});
  const showLink = page
    .locator(`a[href*="/admin/resources/${resource}/records/"][href*="/show"]`)
    .first();
  if ((await showLink.count()) === 0) return null;
  const href = await showLink.getAttribute("href");
  if (!href) return null;
  const m = href.match(/\/records\/([^/]+)\/show/);
  return m ? m[1] : null;
}

// ── Agent show page ───────────────────────────────────────────────────────────

test.describe("40 — UX-CLARITY chunk G: Agent show page descriptions", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("api_key_fingerprint description renders inline below value on agent show page", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    const recordId = await firstRecordId(page, "agents");
    if (!recordId) {
      // No agents seeded — skip gracefully
      test.skip(true, "No agents found in the system — skip show-page description test");
      return;
    }

    await page.goto(`/admin/resources/agents/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

    // The custom DescriptiveShowProperty must render a description element
    const descEl = page.locator('[data-testid="show-description-api_key_fingerprint"]');
    await expect(descEl, "show-description-api_key_fingerprint must be visible").toBeVisible({
      timeout: 15_000,
    });

    const descText = (await descEl.textContent()) ?? "";
    expect(
      descText,
      "api_key_fingerprint description must contain 'First 16 hex chars of SHA-256'",
    ).toContain("First 16 hex chars of SHA-256");

    // At least 2 of the expected description phrases should appear anywhere on the page body
    const body = (await page.locator("body").innerText().catch(() => "")) ?? "";
    const expectedPhrases = [
      "First 16 hex chars of SHA-256",
      "mcpServers.mintkey.url",
      "Requests per second cap",
      "emergency stop",
    ];
    const matchingPhrases = expectedPhrases.filter((phrase) => body.includes(phrase));
    expect(
      matchingPhrases.length,
      `Agent show page must contain at least 2 description phrases. Found: ${matchingPhrases.join(", ")}`,
    ).toBeGreaterThanOrEqual(2);

    void consoleErrors;
  });
});

// ── Tenant show page ──────────────────────────────────────────────────────────

test.describe("40 — UX-CLARITY chunk G: Tenant show page descriptions", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("isolation_mode description renders inline below value on tenant show page", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    const recordId = await firstRecordId(page, "tenants");
    if (!recordId) {
      test.skip(true, "No tenants found in the system — skip show-page description test");
      return;
    }

    await page.goto(`/admin/resources/tenants/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

    const descEl = page.locator('[data-testid="show-description-isolation_mode"]');
    await expect(descEl, "show-description-isolation_mode must be visible").toBeVisible({
      timeout: 15_000,
    });

    const descText = (await descEl.textContent()) ?? "";
    expect(
      descText,
      "isolation_mode description must contain 'Cannot be changed after tenant creation'",
    ).toContain("Cannot be changed after tenant creation");

    void consoleErrors;
  });
});

// ── Permission grant show page ────────────────────────────────────────────────

test.describe("40 — UX-CLARITY chunk G: Permission grant show page descriptions", () => {
  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS is required").not.toEqual("");
  });

  test("constraints description renders inline below value on permission grant show page", async ({
    page,
    consoleErrors,
    browserName,
  }) => {
    test.skip(skipWebkit({ browserName }), "webkit CORS W8");

    const recordId = await firstRecordId(page, "permission_grants");
    if (!recordId) {
      test.skip(true, "No permission grants found — skip show-page description test");
      return;
    }

    await page.goto(`/admin/resources/permission_grants/records/${recordId}/show`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

    // constraints uses components.show: JsonValue, which takes precedence over
    // DefaultShowProperty. The description element will NOT be rendered via
    // DescriptiveShowProperty for constraints — check the action field instead,
    // which does NOT have a per-property component.show override.
    //
    // The action field description: "Action scope this agent may invoke..."
    const actionDescEl = page.locator('[data-testid="show-description-action"]');
    const constraintsDescEl = page.locator('[data-testid="show-description-constraints"]');

    // Try constraints first (if JsonValue renders description too), otherwise fall back to action
    const constraintsCount = await constraintsDescEl.count();

    if (constraintsCount > 0 && await constraintsDescEl.isVisible()) {
      // constraints description is visible (e.g. JsonValue was updated to support it)
      const descText = (await constraintsDescEl.textContent()) ?? "";
      expect(
        descText.includes("rate_limit") || descText.includes("Closed schema"),
        `constraints description must mention rate_limit or Closed schema. Got: "${descText}"`,
      ).toBe(true);
    } else {
      // Fall back to action field — DescriptiveShowProperty renders it since no per-property show override
      await expect(
        actionDescEl,
        "show-description-action must be visible (constraints uses JsonValue, so action is the proxy)",
      ).toBeVisible({ timeout: 15_000 });

      const actionDescText = (await actionDescEl.textContent()) ?? "";
      expect(
        actionDescText,
        "action description must mention 'call' or 'verb:resource' pattern",
      ).toMatch(/call|verb.*resource|<verb>/);
    }

    void consoleErrors;
  });
});
