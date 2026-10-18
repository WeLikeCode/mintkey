/**
 * OPS-DDEE Screenshot capture — Playwright (chromium).
 *
 * Captures screenshots for the 4 deliverables:
 *   1. Service show page with Set Credential CTA
 *   2. Credentials new form pre-filled with service_id
 *   3. Agent created with Copy button visible
 *   4. GitHub template with all 5 fields populated
 *
 * NOT a permanent test — run once for live verification screenshots.
 * Source: OPS-DDEE reporting format.
 */

import { getApiSession } from "../fixtures/session.js";
import { ADMIN_API, TENANT_ID } from "../env.js";
import { test, expect } from "../fixtures/test.js";

const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const PLAYWRIGHT_USER = process.env.PLAYWRIGHT_USER ?? "admin@mintkey.internal";

interface Session { sessionToken: string; csrfToken: string; }

async function getSession(): Promise<Session | null> {
  return getApiSession();
}

test.describe("DDEE screenshots", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "chromium only");

  test.beforeAll(() => {
    expect(process.env.PLAYWRIGHT_PASS ?? "", "PLAYWRIGHT_PASS required").not.toEqual("");
  });

  test("capture all 4 screenshots", async ({ page }) => {
    const session = await getSession();
    const authHeaders = session ? {
      "Content-Type": "application/json",
      Cookie: `mintkey_session=${session.sessionToken}; csrf_token=${session.csrfToken}`,
      "X-Mintkey-Csrf": session.csrfToken,
    } : {};

    const id = uid();
    let svcId = "";
    let agentId = "";

    // ── Screenshot 1: Service show page with Set Credential CTA ────────────
    await page.goto("/admin/resources/services/actions/new", { waitUntil: "domcontentloaded" });
    await page.locator("[data-testid='service-create-form']").waitFor({ timeout: 15_000 });
    await page.locator("[data-testid='field-input-name']").fill(`ddee-svc-${id}`);
    await page.locator("[data-testid='field-input-base_url']").fill("https://api.example.com");
    await page.locator("[data-testid='service-create-submit']").click();
    await page.locator("[data-testid='success-banner']").waitFor({ timeout: 20_000 });
    const viewBtn = page.locator("[data-testid='skip-to-service-btn']");
    const showHref = await viewBtn.getAttribute("href") ?? "";
    const idMatch = showHref.match(/records\/([^/]+)\/show/);
    svcId = idMatch?.[1] ?? "";

    await page.goto(showHref, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.screenshot({ path: "/tmp/ddee-set-credential.png", fullPage: true });

    // ── Screenshot 2: Credentials new form pre-filled ─────────────────────
    await page.goto(`/admin/resources/credentials/actions/new?service_id=${svcId}`, { waitUntil: "domcontentloaded" });
    await page.locator("[data-testid='credential-new-form']").waitFor({ timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1000);
    await page.screenshot({ path: "/tmp/ddee-credential-prefilled.png", fullPage: true });

    // ── Screenshot 3: Agent created with Copy button ──────────────────────
    await page.goto("/admin/resources/agents/actions/new", { waitUntil: "domcontentloaded" });
    await page.locator("[data-testid='agent-create-form']").waitFor({ timeout: 15_000 }).catch(() => {});
    await page.locator("[data-testid='field-input-name']").fill(`ddee-agent-${id}`);
    await page.locator("[data-testid='agent-create-submit']").click();
    await page.locator("[data-testid='agent-created-notice']").waitFor({ timeout: 20_000 });
    agentId = await page.locator("[data-testid='agent-id-value']").innerText().catch(() => "");
    await page.screenshot({ path: "/tmp/ddee-agent-created.png", fullPage: true });

    // ── Screenshot 4: GitHub template with all 5 fields ──────────────────
    await page.goto("/admin/resources/services/actions/new?template=github", { waitUntil: "domcontentloaded" });
    await page.locator("[data-testid='service-create-form']").waitFor({ timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(3000);
    await page.screenshot({ path: "/tmp/ddee-template-prefill.png", fullPage: true });

    // Cleanup
    if (svcId && session) {
      await fetch(`${ADMIN_API}/v1/tenants/${TENANT_ID}/services/${svcId}`, { method: "DELETE", headers: authHeaders }).catch(() => {});
    }
    if (agentId.trim() && session) {
      await fetch(`${ADMIN_API}/v1/tenants/${TENANT_ID}/agents/${agentId.trim()}`, { method: "DELETE", headers: authHeaders }).catch(() => {});
    }
  });
});
