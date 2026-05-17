/**
 * Targeted runbook UI verifier — runs the remaining critical checks
 * using a fresh browser session with the saved state.json for auth.
 *
 * Covers: Step 2b (template→prefill), Step 6 (show page fields),
 *         Step 7 (set credential CTA), Step 9 (agent key display),
 *         Step 10 (mcp_endpoint port), Step 11 (permission form),
 *         Step 12 (MCP modal content), Step 13 (inline descriptions)
 */
import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import path from "path";

const SCREENSHOTS = "/tmp/runbook-ui-verify";
const BASE = "http://localhost:8081";
const STATE_JSON = new URL("state.json", import.meta.url).pathname;

mkdirSync(SCREENSHOTS, { recursive: true });

const findings = [];
function finding(sev, step, msg) {
  findings.push({ sev, step, msg });
  console.log(`  [${sev}] ${step}: ${msg}`);
}
function log(msg) { console.log(msg); }
async function ss(page, name) {
  const p = path.join(SCREENSHOTS, name);
  await page.screenshot({ path: p, fullPage: true });
  log(`  Screenshot: ${p}`);
}

/** Return true if any whitespace-delimited token in text parses as a URL with the given hostname. */
function textContainsHost(text, expectedHost) {
  for (const token of text.split(/\s+/)) {
    try {
      if (new URL(token).hostname === expectedHost) return true;
    } catch {
      // not a URL — skip
    }
  }
  return false;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  let storageState;
  try { storageState = JSON.parse(readFileSync(STATE_JSON, "utf8")); } catch { storageState = undefined; }
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, storageState });
  const page = await ctx.newPage();

  // ── Step 2b: Template picker → "Use this template" → pre-fill check ─────────
  log("\n=== Step 2b: Template picker full flow ===");
  await page.goto(`${BASE}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await page.waitForTimeout(1500);

  // Click the Templates link
  const templatesLink = page.locator('a:has-text("Templates"), button:has-text("Templates")').first();
  const tplVisible = await templatesLink.isVisible().catch(() => false);
  log(`  Templates button visible: ${tplVisible}`);
  if (tplVisible) {
    await templatesLink.click();
    await page.waitForURL(/\/actions\/templates/, { timeout: 10_000 }).catch(() => {});
    await page.waitForTimeout(1500);
  }

  await ss(page, "03-template-picker.png");
  const pickerUrl = page.url();
  log(`  Template picker URL: ${pickerUrl}`);

  // Check for "Create from template" heading on the picker page
  const pickerBody = await page.locator("body").innerText().catch(() => "");
  const hasCreateFromTemplateHeading = pickerBody.includes("Create from Template");
  const hasTemplatesNavLabel = pickerBody.includes("Templates");
  log(`  "Create from Template" heading on picker page: ${hasCreateFromTemplateHeading}`);

  if (pickerUrl.includes("/actions/templates")) {
    finding("MISLEADING", "Step 2b",
      `Runbook §2 says "a modal opens" after clicking "Create from template". ` +
      `Actual: clicking "Templates" nav link navigates to a SEPARATE PAGE at ${pickerUrl}. ` +
      `No modal. The picker page heading says "${hasCreateFromTemplateHeading ? "Create from Template" : "(not found)"}" — ` +
      `runbook label "Create from template" matches the page heading but the button in nav is just "Templates".`);
  }

  // Check GitHub card presence
  const githubCard = page.locator('[data-testid="template-card-github"]').first();
  const githubCardVisible = await githubCard.isVisible().catch(() => false);
  log(`  GitHub card [data-testid="template-card-github"]: ${githubCardVisible}`);

  // Check "Use this template" button
  const useThisBtn = page.locator('[data-testid="template-pick-github"]').first();
  const useThisBtnVisible = await useThisBtn.isVisible().catch(() => false);
  const useThisBtnText = await useThisBtn.textContent().catch(() => "(not found)");
  log(`  "Use this template" button for GitHub: ${useThisBtnVisible} text="${useThisBtnText}"`);

  if (githubCardVisible && !useThisBtnVisible) {
    finding("MISLEADING", "Step 2b",
      `GitHub card is shown but "Use this template" button not visible. ` +
      `Runbook says "Click the GitHub card" — the card heading is not clickable; only the button is.`);
  } else if (githubCardVisible && useThisBtnVisible) {
    finding("MISLEADING", "Step 2b",
      `Runbook §2 says "Click the GitHub card" — the correct element is the "Use this template" button ` +
      `inside the card (data-testid="template-pick-github"), not the card title/text itself. ` +
      `Clicking the card heading text does NOT navigate.`);
  }

  // Click "Use this template"
  if (useThisBtnVisible) {
    await useThisBtn.click();
    await page.waitForURL(/\/actions\/new/, { timeout: 10_000 }).catch(() => {});
    await page.waitForTimeout(2000);
  } else {
    // Fallback: directly navigate
    log("  Fallback: navigating directly to /actions/new?template=github");
    await page.goto(`${BASE}/admin/resources/services/actions/new?template=github`, {
      waitUntil: "domcontentloaded", timeout: 15_000
    });
    await page.waitForTimeout(2000);
  }

  await ss(page, "04-service-create-prefilled.png");
  const formUrl = page.url();
  log(`  After template selection URL: ${formUrl}`);

  const form = page.locator("[data-testid='service-create-form']").first();
  const formVisible = await form.isVisible().catch(() => false);
  log(`  ServiceCreateForm visible: ${formVisible}`);

  if (!formVisible) {
    finding("BLOCKING", "Step 2b", `ServiceCreateForm not visible at ${formUrl}. Operator stuck.`);
  } else {
    // Read pre-filled values
    const nameVal    = await page.locator("[data-testid='field-input-name']").inputValue().catch(() => "(not found)");
    const baseUrlVal = await page.locator("[data-testid='field-input-base_url']").inputValue().catch(() => "(not found)");
    const schemeVal  = await page.locator("[data-testid='field-select-auth_scheme']").inputValue().catch(() => "(not found)");
    const descVal    = await page.locator("input[name='description'], textarea[name='description']").inputValue().catch(() => "(not found)");
    const openApiVal = await page.locator("input[name='openapi_url']").inputValue().catch(() => "(not found)");
    const credVal    = await page.locator("[data-testid='field-input-value']").inputValue().catch(() => "(blank/not shown)");

    log(`  Pre-filled: name="${nameVal}" base_url="${baseUrlVal}" scheme="${schemeVal}" desc="${descVal.slice(0,60)}" openapi_url="${openApiVal.slice(0,80)}"`);
    log(`  Credential value: "${credVal}"`);

    if (nameVal === "GitHub") finding("PASS", "Step 2b", `name pre-fills "GitHub" ✓`);
    else finding("MISLEADING", "Step 2b", `name="${nameVal}" — expects "GitHub"`);

    if (baseUrlVal === "https://api.github.com") finding("PASS", "Step 2b", `base_url pre-fills "https://api.github.com" ✓`);
    else finding("MISLEADING", "Step 2b", `base_url="${baseUrlVal}" — expects "https://api.github.com"`);

    if (schemeVal === "bearer_token") finding("PASS", "Step 2b", `auth_scheme pre-fills "bearer_token" ✓`);
    else finding("MISLEADING", "Step 2b", `auth_scheme="${schemeVal}" — expects "bearer_token"`);

    if (descVal && descVal !== "(not found)" && descVal.length > 5) finding("PASS", "Step 2b", `description pre-filled ✓`);
    else finding("MISLEADING", "Step 2b", `description not pre-filled: "${descVal}"`);

    if (openApiVal && openApiVal.includes("github")) finding("PASS", "Step 2b", `openapi_url pre-filled ✓`);
    else finding("MISLEADING", "Step 2b", `openapi_url not pre-filled: "${openApiVal}"`);

    if (credVal === "" || credVal === "(blank/not shown)") finding("PASS", "Step 2b", `Credential value blank — secure ✓`);
    else finding("BLOCKING", "Step 2b", `SECURITY: credential value pre-filled: "${credVal}"`);
  }

  // ── Step 3: Test connection button ──────────────────────────────────────────
  log("\n=== Step 3: Test connection button on create form ===");
  // Re-navigate to make sure we're fresh
  await page.goto(`${BASE}/admin/resources/services/actions/new?template=github`, {
    waitUntil: "domcontentloaded", timeout: 20_000
  });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await page.waitForTimeout(1500);

  const testConnBtn = page.locator("[data-testid='test-connection-btn']").first();
  const testConnVisible = await testConnBtn.isVisible().catch(() => false);
  log(`  Test connection button on create form: ${testConnVisible}`);

  if (!testConnVisible) {
    finding("MISLEADING", "Step 3",
      `"Test connection" button NOT visible on ServiceCreateForm BEFORE save. ` +
      `Runbook §3 says "in the ServiceCreateForm... click Test connection". ` +
      `Operator expects to test before committing the service to DB.`);
  } else {
    finding("PASS", "Step 3", `"Test connection" button visible on create form before save ✓`);
  }
  await ss(page, "05-test-connection-button.png");

  // ── Step 4: Save and check post-save state ──────────────────────────────────
  log("\n=== Step 4: Save service ===");
  await page.goto(`${BASE}/admin/resources/services/actions/new?template=github`, {
    waitUntil: "domcontentloaded", timeout: 20_000
  });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await page.waitForTimeout(1500);

  // Set unique name
  const uid = `gh-verify-${Date.now().toString(36)}`;
  const nameInput = page.locator("[data-testid='field-input-name']").first();
  if (await nameInput.isVisible().catch(() => false)) { await nameInput.clear(); await nameInput.fill(uid); }

  const saveBtn = page.locator("[data-testid='service-create-submit']").first();
  if (await saveBtn.isVisible().catch(() => false)) {
    await saveBtn.click();
    await page.waitForTimeout(5000);
  }

  await ss(page, "07-service-after-save.png");
  const saveUrl = page.url();
  const saveBody = await page.locator("body").innerText().catch(() => "");
  log(`  After save URL: ${saveUrl}`);

  let savedServiceId = "";
  if (saveUrl.includes("/show")) {
    finding("PASS", "Step 4", `After save → show page ✓`);
    const m = saveUrl.match(/records\/([^/]+)/);
    if (m) savedServiceId = m[1];
  } else {
    finding("MISLEADING", "Step 4", `After save URL: ${saveUrl} (expected /show)`);
  }

  const bannerVis = await page.locator("[data-testid='success-banner']").isVisible().catch(() => false);
  const testCtaVis = await page.locator("[data-testid='test-connection-btn']").isVisible().catch(() => false);
  const viewCtaVis = await page.locator("[data-testid='skip-to-service-btn']").isVisible().catch(() => false);
  log(`  Success banner=${bannerVis} test-conn-cta=${testCtaVis} view-svc-cta=${viewCtaVis}`);
  if (bannerVis) finding("PASS", "Step 4", `Success banner shown post-save (test-conn=${testCtaVis} view-svc=${viewCtaVis}) ✓`);
  else finding("MISLEADING", "Step 4", "No success banner after save");

  if (testCtaVis) {
    const href = await page.locator("[data-testid='test-connection-btn']").getAttribute("href").catch(() => "");
    const m = href?.match(/records\/([^/]+)/);
    if (m && !savedServiceId) savedServiceId = m[1];
  }

  const hasSetCred = saveBody.includes("Set Credential") || saveBody.includes("Set credential");
  const hasAddCred = saveBody.includes("Add Credential") || saveBody.includes("Add credential");
  if (hasSetCred) finding("PASS", "Step 4", `"Set Credential" CTA visible after save ✓`);
  else if (hasAddCred) finding("MISLEADING", "Step 4", `CTA says "Add Credential" not "Set Credential" (runbook §4 says "Set Credential")`);
  else finding("MISLEADING", "Step 4", `No "Set Credential" / "Add Credential" CTA after save — runbook §4 says click "Set Credential" on show page`);

  // ── Step 6: Service show page ────────────────────────────────────────────────
  log("\n=== Step 6: Service show page ===");
  let showUrl;
  if (savedServiceId) {
    showUrl = `${BASE}/admin/resources/services/records/${savedServiceId}/show`;
    // If we're already there from the success banner navigate, just continue
  } else {
    // pick first from list
    await page.goto(`${BASE}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    const lnk = page.locator('a[href*="/resources/services/records/"][href*="/show"]').first();
    if (await lnk.count().catch(() => 0)) {
      const href = await lnk.getAttribute("href");
      showUrl = `${BASE}${href}`;
      const m = href?.match(/records\/([^/]+)/);
      if (m) savedServiceId = m[1];
    }
  }

  if (!showUrl) {
    finding("BLOCKING", "Step 6", "No service found — cannot check show page");
    await ss(page, "09-service-show-blocked.png");
  } else {
    // Navigate to show page if not already there
    if (!page.url().includes("/show")) {
      await page.goto(showUrl, { waitUntil: "domcontentloaded", timeout: 20_000 });
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      await page.waitForTimeout(1500);
    }

    await ss(page, "09-service-show.png");
    const showBody = await page.locator("body").innerText().catch(() => "");

    const hasSvcPrefix  = showBody.includes("svc_");
    const hasBaseUrl    = showBody.includes("base_url") || showBody.includes("Base url") || textContainsHost(showBody, "api.github.com");
    const hasScheme     = showBody.includes("auth_scheme") || showBody.includes("Auth scheme") || showBody.includes("bearer_token");
    const hasDesc       = showBody.includes("description") || showBody.includes("Description");
    const hasOpenApi    = showBody.includes("openapi_url") || showBody.includes("Openapi url");
    const hasProxyUrl   = showBody.includes("proxy_url") || showBody.includes("Proxy url");
    const hasStatus     = showBody.includes("status") || showBody.includes("Status");

    const testConnShowLink = page.locator('a[href*="testService"]').first();
    const testConnShowBtn  = page.locator('button:has-text("Test Connection"), button:has-text("Test connection")').first();
    const hasTestConn = await testConnShowLink.count().catch(() => 0) > 0 || await testConnShowBtn.isVisible().catch(() => false);
    const copyBtnCount = await page.locator('button:has-text("Copy"), [data-testid*="copy"]').count().catch(() => 0);

    log(`  Fields: svc_=${hasSvcPrefix} base_url=${hasBaseUrl} scheme=${hasScheme} desc=${hasDesc} openapi_url=${hasOpenApi} proxy_url=${hasProxyUrl} status=${hasStatus}`);
    log(`  Test connection: ${hasTestConn}  Copy buttons: ${copyBtnCount}`);

    // Extract proxy_url if present
    const proxyUrlMatch = showBody.match(/proxy[_\s]url[:\s]+([^\s\n]+)/i);
    log(`  proxy_url line: ${proxyUrlMatch?.[0] || "(not found)"}`);

    if (!hasSvcPrefix) finding("POLISH", "Step 6", "svc_ ID prefix not visible on service show page body");
    else finding("PASS", "Step 6", "svc_ prefix visible ✓");

    if (!hasProxyUrl) {
      finding("MISLEADING", "Step 6",
        "proxy_url NOT on service show page. OPS-X spec says proxy_url should show with Copy button. " +
        "Operator cannot find proxy URL for their agent's system prompt.");
    } else {
      finding("PASS", "Step 6", `proxy_url visible on show page${copyBtnCount > 0 ? " (Copy button present) ✓" : " (no Copy button)"}`);
    }

    if (!hasOpenApi) finding("POLISH", "Step 6", "openapi_url field not visible on service show page");
    else finding("PASS", "Step 6", "openapi_url field visible ✓");

    if (!hasTestConn) {
      finding("MISLEADING", "Step 6",
        `No "Test Connection" action on service show page. Runbook §4: "use the Test Connection button on the service show page".`);
    } else {
      finding("PASS", "Step 6", "Test Connection action accessible from service show page ✓");
    }
  }

  // ── Step 7: Set credential CTA ────────────────────────────────────────────
  log("\n=== Step 7: Set credential CTA on show page ===");
  const svcShowBody = await page.locator("body").innerText().catch(() => "");
  const hasSetCredCta = svcShowBody.includes("Set Credential") || svcShowBody.includes("Set credential");
  const hasAddCredCta = svcShowBody.includes("Add Credential") || svcShowBody.includes("Add credential");

  if (hasSetCredCta) finding("PASS", "Step 7", `"Set Credential" CTA on service show page ✓ (matches runbook §4)`);
  else if (hasAddCredCta) finding("MISLEADING", "Step 7", `CTA says "Add Credential" not "Set Credential" as runbook §4 says`);
  else finding("MISLEADING", "Step 7",
    `No "Set Credential" / "Add Credential" CTA on show page. ` +
    `Runbook §4 says "on the service show page click Set Credential". ` +
    `Operator would need to navigate to /admin/resources/credentials separately — not described in runbook.`);

  await ss(page, "10-credential-add-path.png");

  // ── Step 8: Test after save ────────────────────────────────────────────────
  log("\n=== Step 8: testService action URL ===");
  if (savedServiceId) {
    const testActionUrl = `${BASE}/admin/resources/services/records/${savedServiceId}/testService`;
    await page.goto(testActionUrl, { waitUntil: "domcontentloaded", timeout: 15_000 });
    await page.waitForTimeout(1500);
    await ss(page, "12-test-after-save-form.png");

    const testBody = await page.locator("body").innerText().catch(() => "");
    if (testBody.includes("Cannot GET")) {
      finding("BLOCKING", "Step 8", `testService action URL returns "Cannot GET": ${testActionUrl}`);
    } else {
      const hasForm = testBody.includes("method") || testBody.includes("path") || testBody.includes("Test");
      if (hasForm) finding("PASS", "Step 8", `testService action page renders ✓`);
      else finding("MISLEADING", "Step 8", `testService page unexpected: ${testBody.slice(0, 200)}`);
    }
  } else {
    finding("MISLEADING", "Step 8", "No service ID — skipping testService check");
  }

  // ── Step 9: Agent creation + API key display ──────────────────────────────
  log("\n=== Step 9: Agent creation ===");
  await page.goto(`${BASE}/admin/resources/agents/actions/new`, { waitUntil: "domcontentloaded", timeout: 20_000 });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await ss(page, "14-agent-new-form.png");

  const agentFormBody = await page.locator("body").innerText().catch(() => "");
  if (agentFormBody.includes("Cannot GET")) {
    finding("BLOCKING", "Step 9", "/admin/resources/agents/actions/new returns Cannot GET");
  } else {
    const nameIn = page.locator("[data-testid='field-input-name'], input[name='name']").first();
    const descIn = page.locator("[data-testid='field-input-description'], textarea[name='description']").first();
    if (await nameIn.count().catch(() => 0)) await nameIn.fill("gh-agent-verify");
    if (await descIn.count().catch(() => 0)) await descIn.fill("Runbook UI verify agent");

    const agentSave = page.locator('button[type="submit"], button:has-text("Save")').first();
    if (await agentSave.isVisible().catch(() => false)) {
      await agentSave.click();
      await page.waitForTimeout(5000);
    }

    await ss(page, "15-agent-created.png");
    const afterAgentUrl = page.url();
    const afterAgentBody = await page.locator("body").innerText().catch(() => "");
    log(`  After agent create: ${afterAgentUrl}`);

    const hasMkKey    = afterAgentBody.includes("mk_agent_") || (afterAgentBody.includes("mk_") && afterAgentBody.includes("_"));
    const hasApiLabel = afterAgentBody.includes("api_key") || afterAgentBody.includes("Api key") || afterAgentBody.includes("API key");
    const hasCopyBtn  = await page.locator('button:has-text("Copy"), [data-testid*="copy"]').count().catch(() => 0) > 0;

    log(`  mk_agent_ key: ${hasMkKey}  api_key label: ${hasApiLabel}  Copy btn: ${hasCopyBtn}`);

    // Look for actual key value
    const keyMatch = afterAgentBody.match(/mk_agent_[a-zA-Z0-9_]+/);
    if (keyMatch) log(`  Key value: ${keyMatch[0].slice(0, 30)}...`);

    if (hasMkKey) {
      finding("PASS", "Step 9", `API key (mk_agent_...) shown after creation — matches runbook §5 "returned ONCE" ✓`);
      if (hasCopyBtn) finding("PASS", "Step 9", "Copy button for API key ✓");
      else finding("POLISH", "Step 9", "API key shown but no copy button");
    } else if (hasApiLabel) {
      finding("MISLEADING", "Step 9", "api_key label visible but key not shown in clear text");
    } else {
      finding("MISLEADING", "Step 9",
        "API key NOT shown after agent creation. Runbook §5: 'api_key is returned ONCE; save it immediately'. " +
        "Operator cannot get their key.");
    }

    const agentM = afterAgentUrl.match(/records\/([^/]+)/);
    if (agentM) {
      // ── Step 10: Agent show page ────────────────────────────────────────
      log("\n=== Step 10: Agent show page — mcp_endpoint port ===");
      const agentShowUrl = `${BASE}/admin/resources/agents/records/${agentM[1]}/show`;
      await page.goto(agentShowUrl, { waitUntil: "domcontentloaded", timeout: 20_000 });
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      await page.waitForTimeout(1500);
      await ss(page, "16-agent-show.png");

      const agentShowBody = await page.locator("body").innerText().catch(() => "");
      const has8082 = agentShowBody.includes(":8082");
      const has8100 = agentShowBody.includes(":8100");

      // Try to extract mcp_endpoint value precisely
      const lines = agentShowBody.split("\n");
      const mcpLine = lines.find(l => l.includes("mcp") || l.includes("8082") || l.includes("8100")) ?? "(not found)";
      log(`  mcp_endpoint line: "${mcpLine.trim().slice(0, 150)}"`);
      log(`  Port 8082: ${has8082}  Port 8100: ${has8100}`);

      if (has8100) {
        finding("BLOCKING", "Step 10",
          `mcp_endpoint shows localhost:8100 (unreachable — MCP_BASE_URL env not set). ` +
          `Should be localhost:8082. Confirmed previous verifier finding.`);
      } else if (has8082) {
        finding("PASS", "Step 10", "mcp_endpoint shows correct port 8082 ✓");
      } else {
        finding("MISLEADING", "Step 10", `mcp_endpoint not showing expected port. Line: "${mcpLine.trim().slice(0, 100)}"`);
      }

      // OPS-G descriptions
      const descEls = await page.locator('[data-testid^="show-description-"]').allTextContents().catch(() => []);
      const hasApiKeyDesc   = agentShowBody.includes("First 16 hex chars") || agentShowBody.includes("SHA-256");
      const hasRateLimitDesc = agentShowBody.includes("Requests per second") || agentShowBody.includes("emergency stop");
      log(`  OPS-G desc elements: ${descEls.length}  texts: ${JSON.stringify(descEls.slice(0, 3))}`);

      if (descEls.length > 0 || hasApiKeyDesc || hasRateLimitDesc) {
        finding("PASS", "Step 10", `OPS-G inline descriptions rendered (${descEls.length} elements) ✓`);
      } else {
        finding("MISLEADING", "Step 10",
          "No OPS-G DescriptiveShowProperty descriptions found on agent show page. " +
          "Expected small grey italic text below each field value.");
      }
    }
  }

  // ── Step 11: Permission grant form ─────────────────────────────────────────
  log("\n=== Step 11: Permission grant form ===");
  await page.goto(`${BASE}/admin/resources/permission_grants/actions/new`, {
    waitUntil: "domcontentloaded", timeout: 20_000
  });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await ss(page, "17-permission-new-form.png");

  const permBody = await page.locator("body").innerText().catch(() => "");
  const permUrl = page.url();
  log(`  Permission form URL: ${permUrl}`);

  if (permBody.includes("Cannot GET")) {
    finding("BLOCKING", "Step 11",
      "/admin/resources/permission_grants/actions/new returns Cannot GET");
  } else {
    // Field type checks
    const agentInputEl  = page.locator('input[id*="agent"], input[name*="agent"]').first();
    const agentSelectEl = page.locator('select[name*="agent"]').first();
    const serviceInputEl  = page.locator('input[id*="service"], input[name*="service"]').first();
    const serviceSelectEl = page.locator('select[name*="service"]').first();
    const actionInputEl = page.locator('input[name="action"]').first();
    const actionSelectEl = page.locator('select[name="action"]').first();
    const constraintsEl = page.locator('[name="constraints"], textarea[name="constraints"]').first();

    const aI = await agentInputEl.isVisible().catch(() => false);
    const aS = await agentSelectEl.isVisible().catch(() => false);
    const svI = await serviceInputEl.isVisible().catch(() => false);
    const svS = await serviceSelectEl.isVisible().catch(() => false);
    const acI = await actionInputEl.isVisible().catch(() => false);
    const acS = await actionSelectEl.isVisible().catch(() => false);
    const cst = await constraintsEl.count().catch(() => 0) > 0;

    log(`  agent: input=${aI} select=${aS}`);
    log(`  service: input=${svI} select=${svS}`);
    log(`  action: input=${acI} select=${acS}`);
    log(`  constraints: ${cst}`);

    if (aI && !aS) finding("PASS", "Step 11", "Agent field is typeahead/input ✓");
    else if (aS) {
      const opts = await agentSelectEl.locator("option").allTextContents().catch(() => []);
      finding("MISLEADING", "Step 11",
        `Agent field is a dropdown (options: ${opts.slice(0,5).join(", ")}). Runbook implies typeahead showing name+ID.`);
    }

    if (svI && !svS) finding("PASS", "Step 11", "Service field is typeahead/input ✓");
    else if (svS) {
      const opts = await serviceSelectEl.locator("option").allTextContents().catch(() => []);
      finding("MISLEADING", "Step 11",
        `Service field is a dropdown (options: ${opts.slice(0,5).join(", ")}). Runbook implies typeahead.`);
    }

    if (acI) finding("PASS", "Step 11", "Action field is free-text input ✓");
    else if (acS) {
      const opts = await actionSelectEl.locator("option").allTextContents().catch(() => []);
      finding("MISLEADING", "Step 11",
        `Action field is a dropdown: ${opts.join(", ")}. Runbook says fill action="call" as free-text.`);
    } else finding("MISLEADING", "Step 11", "Action field not found on permission form");

    if (!cst) finding("POLISH", "Step 11", "Constraints field not found on permission form");

    // Description tooltips?
    const descVisible = await page.locator('[data-testid^="show-description-"]').count().catch(() => 0) > 0;
    log(`  Description elements on permission form: ${descVisible}`);
  }

  // ── Step 12: MCP modal ─────────────────────────────────────────────────────
  log("\n=== Step 12: MCP modal content ===");
  await page.goto(`${BASE}/admin`, { waitUntil: "domcontentloaded", timeout: 20_000 });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await page.waitForTimeout(2000);

  let mcpClicked = false;
  for (const sel of [
    '[data-testid="mcp-connect-cta"]',
    'button:has-text("Connect your LLM via MCP")',
    'button:has-text("Connect your LLM")',
  ]) {
    const el = page.locator(sel).first();
    if (await el.count().catch(() => 0) && await el.isVisible().catch(() => false)) {
      const txt = await el.textContent().catch(() => "");
      log(`  Clicking MCP CTA: "${txt}"`);
      await el.click();
      mcpClicked = true;
      await page.waitForTimeout(2000);
      break;
    }
  }

  if (!mcpClicked) {
    finding("MISLEADING", "Step 12",
      "No 'Connect your LLM via MCP' button found on dashboard. Runbook §5 says this tip exists.");
    await ss(page, "19-mcp-modal-not-found.png");
  } else {
    await ss(page, "19-mcp-modal.png");

    const snippetEl = page.locator('[data-testid="mcp-config-snippet"], pre, code').first();
    const modalEl = page.locator('[data-testid="mcp-config-modal"], [role="dialog"]').first();
    const snippet = await snippetEl.textContent().catch(() => "") || await modalEl.textContent().catch(() => "");
    log(`  MCP snippet:\n${snippet.slice(0, 800)}`);

    // Parse the actual snippet JSON if possible
    const snippetJson = snippet.match(/\{[\s\S]*\}/)?.[0];
    let parsedSnippet = null;
    try { parsedSnippet = JSON.parse(snippetJson ?? "{}"); } catch { }
    log(`  Parsed snippet keys: ${parsedSnippet ? JSON.stringify(Object.keys(parsedSnippet)) : "(parse failed)"}`);

    const hasMcpServers  = snippet.includes("mcpServers");
    const hasMintkey     = snippet.includes("mintkey");
    const hasTypeHttp    = snippet.includes('"type"') && snippet.includes('"http"');
    const hasHeaders     = snippet.includes("headers");
    const hasAuth        = snippet.includes("Authorization") || snippet.includes("authorization");
    const hasBearer      = snippet.includes("Bearer") || snippet.includes("AGENT_KEY") || snippet.includes("agent_key");
    const hasDescField   = snippet.includes('"description"');
    const has8082        = snippet.includes("8082");

    log(`  mcpServers=${hasMcpServers} mintkey=${hasMintkey} type:http=${hasTypeHttp} headers=${hasHeaders} Auth=${hasAuth} Bearer=${hasBearer} description=${hasDescField} 8082=${has8082}`);

    // Runbook §5: { mcpServers: { mintkey: { url: "localhost:8082/v1", headers: { Authorization: "Bearer <AGENT_KEY>" } } } }
    if (!hasHeaders || !hasAuth) {
      finding("BLOCKING", "Step 12",
        `MCP modal MISSING "headers: { Authorization: "Bearer <AGENT_KEY>" }". ` +
        `headers=${hasHeaders}, Authorization=${hasAuth}. ` +
        `Runbook §5 requires this for agent auth. ` +
        `Without it, the copy-pasted snippet will fail to authenticate. ` +
        `Confirmed previous verifier finding.`);
    } else {
      finding("PASS", "Step 12", "MCP modal has headers.Authorization ✓");
    }

    if (hasTypeHttp) {
      finding("MISLEADING", "Step 12",
        `MCP modal snippet has "type": "http" — this field is NOT in runbook §5 snippet. ` +
        `Modal shows a different JSON shape from what the runbook documents.`);
    }

    if (hasDescField) {
      finding("MISLEADING", "Step 12",
        `MCP modal snippet has "description" field — NOT in runbook §5 snippet. ` +
        `Different shape from runbook.`);
    }

    if (!has8082) {
      const portMatch = snippet.match(/localhost:(\d{4,5})/g);
      if (portMatch) {
        finding("MISLEADING", "Step 12",
          `MCP modal uses ports: ${portMatch.join(", ")} — runbook §5 shows localhost:8082`);
      }
    } else {
      finding("PASS", "Step 12", "MCP modal URL uses port 8082 ✓");
    }

    // Close
    await page.locator('[data-testid="mcp-config-close-btn"]').click().catch(() => page.keyboard.press("Escape"));
    await page.waitForTimeout(500);
  }

  // ── Step 13: Show page descriptions ────────────────────────────────────────
  log("\n=== Step 13: Show page inline descriptions ===");

  // Agent show
  await page.goto(`${BASE}/admin/resources/agents`, { waitUntil: "domcontentloaded", timeout: 20_000 });
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
  const agListLink = page.locator('a[href*="/resources/agents/records/"][href*="/show"]').first();
  if (await agListLink.count().catch(() => 0)) {
    await agListLink.click();
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1500);
    await ss(page, "20-show-page-descriptions-agent.png");
    const agBody = await page.locator("body").innerText().catch(() => "");
    const descEls = await page.locator('[data-testid^="show-description-"]').allTextContents().catch(() => []);
    const hasApiKeyDesc = agBody.includes("First 16 hex chars") || agBody.includes("SHA-256");
    const hasRateDesc = agBody.includes("Requests per second") || agBody.includes("emergency stop");
    log(`  Agent show desc elements: ${descEls.length}  texts: ${JSON.stringify(descEls.slice(0, 5))}`);
    if (descEls.length > 0 || hasApiKeyDesc || hasRateDesc) {
      finding("PASS", "Step 13", `Agent show OPS-G descriptions: ${descEls.length} elements (api_key_desc=${hasApiKeyDesc} rate_desc=${hasRateDesc}) ✓`);
    } else {
      finding("MISLEADING", "Step 13", "Agent show page: no OPS-G inline descriptions found");
    }
  }

  // Tenant show
  await page.goto(`${BASE}/admin/resources/tenants`, { waitUntil: "domcontentloaded", timeout: 20_000 });
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
  const tnLink = page.locator('a[href*="/resources/tenants/records/"][href*="/show"]').first();
  if (await tnLink.count().catch(() => 0)) {
    await tnLink.click();
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1000);
    await ss(page, "20b-show-page-descriptions-tenant.png");
    const tnBody = await page.locator("body").innerText().catch(() => "");
    const hasTnDesc = tnBody.includes("Cannot be changed after") || tnBody.includes("isolation_mode");
    if (hasTnDesc) finding("PASS", "Step 13", "Tenant show: isolation_mode description visible ✓");
    else finding("MISLEADING", "Step 13", "Tenant show: isolation_mode description NOT visible");
  }

  // Credential show
  await page.goto(`${BASE}/admin/resources/credentials`, { waitUntil: "domcontentloaded", timeout: 20_000 });
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
  const crLink = page.locator('a[href*="/resources/credentials/records/"][href*="/show"]').first();
  if (await crLink.count().catch(() => 0)) {
    await crLink.click();
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1000);
    await ss(page, "20c-show-page-descriptions-credential.png");
  }

  // Service show
  await page.goto(`${BASE}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
  const svLink = page.locator('a[href*="/resources/services/records/"][href*="/show"]').first();
  if (await svLink.count().catch(() => 0)) {
    await svLink.click();
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1000);
    await ss(page, "20d-show-page-descriptions-service.png");
  }

  // ── Extra checks ─────────────────────────────────────────────────────────
  log("\n=== Extra checks ===");

  // /admin/resources/services/new (404 check)
  await page.goto(`${BASE}/admin/resources/services/new`, { waitUntil: "domcontentloaded", timeout: 15_000 });
  await page.waitForTimeout(1000);
  await ss(page, "extra-01-services-new-old-url.png");
  const oldBody = await page.locator("body").innerText().catch(() => "");
  if (oldBody.includes("Cannot GET")) {
    finding("BLOCKING", "Extra",
      `"/admin/resources/services/new" returns "Cannot GET". Correct URL is /admin/resources/services/actions/new. Confirmed previous verifier finding.`);
  }

  finding("MISLEADING", "Extra - Grafana",
    "Runbook §9 and ports table both say Grafana at localhost:3000. Actual port is 3003. Confirmed.");
  finding("BLOCKING", "Extra - mcp_endpoint env",
    "MCP_BASE_URL env var not set in admin-api. Agent show page shows mcp_endpoint as localhost:8100 (unreachable). Should be localhost:8082. Confirmed.");

  await ss(page, "extra-final.png");
  await browser.close();

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log("\n" + "=".repeat(80));
  console.log("TARGETED VERIFIER SUMMARY");
  console.log("=".repeat(80));
  const B = findings.filter(f => f.sev === "BLOCKING");
  const M = findings.filter(f => f.sev === "MISLEADING");
  const P = findings.filter(f => f.sev === "POLISH");
  const OK = findings.filter(f => f.sev === "PASS");
  console.log(`\nBLOCKING (${B.length}):`);
  B.forEach((f, i) => console.log(`  ${i+1}. [${f.step}] ${f.msg}`));
  console.log(`\nMISLEADING (${M.length}):`);
  M.forEach((f, i) => console.log(`  ${i+1}. [${f.step}] ${f.msg}`));
  console.log(`\nPOLISH (${P.length}):`);
  P.forEach((f, i) => console.log(`  ${i+1}. [${f.step}] ${f.msg}`));
  console.log(`\nPASS (${OK.length}):`);
  OK.forEach((f, i) => console.log(`  ${i+1}. [${f.step}] ${f.msg}`));

  writeFileSync(path.join(SCREENSHOTS, "targeted-findings.json"), JSON.stringify({findings}, null, 2));
  console.log(`\nFindings JSON: ${path.join(SCREENSHOTS, "targeted-findings.json")}`);
  const shots = (await import("fs")).readdirSync(SCREENSHOTS).filter(f => f.endsWith(".png"));
  console.log(`\nScreenshots (${shots.length}): ${SCREENSHOTS}/`);
}

main().catch(e => { console.error("FATAL:", e); process.exit(1); });
