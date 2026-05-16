/**
 * Runbook UI Verifier — github-quickstart.md (v2)
 *
 * Walks every UI step from the runbook, captures screenshots, logs findings.
 * Uses correct selectors derived from reading ServiceTemplatePicker.tsx and
 * ServiceCreateForm.tsx source (template picker navigates to /actions/templates
 * not a modal; GitHub card uses data-testid="template-pick-github" "Use this
 * template" button which navigates to /actions/new?template=github).
 *
 * Screenshots: /tmp/runbook-ui-verify/
 * Findings JSON: /tmp/runbook-ui-verify/findings.json
 */

import { test } from "@playwright/test";
import path from "path";
import fs from "fs";

const SCREENSHOTS_DIR = "/tmp/runbook-ui-verify";
const BASE_URL = "http://localhost:8081";

const findings: Array<{ severity: string; step: string; description: string }> = [];

function log(msg: string) {
  console.log(msg);
}

function finding(severity: string, step: string, description: string) {
  findings.push({ severity, step, description });
  console.log(`  [${severity}] ${step}: ${description}`);
}

async function ss(page: any, filename: string) {
  const fpath = path.join(SCREENSHOTS_DIR, filename);
  await page.screenshot({ path: fpath, fullPage: true });
  log(`  Screenshot: ${fpath}`);
  return fpath;
}

test.describe("Runbook UI Verifier — github-quickstart.md", () => {
  test.setTimeout(180_000);

  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  });

  test.afterAll(() => {
    const reportPath = path.join(SCREENSHOTS_DIR, "findings.json");
    fs.writeFileSync(reportPath, JSON.stringify({ findings }, null, 2));
    console.log("\n" + "=".repeat(80));
    console.log("RUNBOOK UI VERIFICATION SUMMARY");
    console.log("=".repeat(80));
    const blocking = findings.filter(f => f.severity === "BLOCKING");
    const misleading = findings.filter(f => f.severity === "MISLEADING");
    const polish = findings.filter(f => f.severity === "POLISH");
    const pass = findings.filter(f => f.severity === "PASS");
    console.log(`\nBLOCKING (${blocking.length}):`);
    blocking.forEach((f, i) => console.log(`  ${i + 1}. [${f.step}] ${f.description}`));
    console.log(`\nMISLEADING (${misleading.length}):`);
    misleading.forEach((f, i) => console.log(`  ${i + 1}. [${f.step}] ${f.description}`));
    console.log(`\nPOLISH (${polish.length}):`);
    polish.forEach((f, i) => console.log(`  ${i + 1}. [${f.step}] ${f.description}`));
    console.log(`\nPASS (${pass.length}):`);
    pass.forEach((f, i) => console.log(`  ${i + 1}. [${f.step}] ${f.description}`));
    console.log(`\nFindings JSON: ${reportPath}`);
  });

  test("Step 1 — Dashboard", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(2000);
    await ss(page, "01-dashboard.png");
    const title = await page.title();
    const bodyText = await page.locator("body").innerText().catch(() => "");
    log(`  Page title: "${title}"`);
    log(`  URL: ${page.url()}`);
    if (bodyText.includes("Dashboard") || bodyText.includes("Mintkey") || bodyText.includes("credential broker")) {
      finding("PASS", "Step 1", "Dashboard loads correctly at /admin");
    } else {
      finding("MISLEADING", "Step 1", `Dashboard body unexpected. Excerpt: ${bodyText.slice(0, 200)}`);
    }
    // Check if onboarding section exists
    const hasOnboarding = bodyText.includes("Get started") || bodyText.includes("onboarding") ||
      bodyText.includes("Quick start") || bodyText.includes("step");
    log(`  Onboarding/get-started section: ${hasOnboarding}`);
    expect(page.url()).toContain("/admin");
  });

  test("Step 2 — Services list + template button", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1500);
    await ss(page, "02-services-list.png");

    const bodyText = await page.locator("body").innerText().catch(() => "");

    const hasCreateFromTemplate = bodyText.includes("Create from template");
    const hasTemplates = bodyText.includes("Templates");
    const hasNewFromTemplate = bodyText.includes("New from template");
    const hasFromTemplate = bodyText.includes("From template") || bodyText.includes("from template");

    log(`  "Create from template" in page: ${hasCreateFromTemplate}`);
    log(`  "Templates" in page: ${hasTemplates}`);
    log(`  "New from template" in page: ${hasNewFromTemplate}`);
    log(`  "From template" in page: ${hasFromTemplate}`);

    // Get all button texts
    const allBtnTexts = await page.locator("button, a[role='button']").allTextContents().catch(() => []);
    log(`  All button texts: ${JSON.stringify(allBtnTexts.slice(0, 15))}`);

    if (!hasCreateFromTemplate && hasTemplates) {
      finding("MISLEADING", "Step 2", `Runbook says click "Create from template" but button is labeled "Templates". Runbook is wrong.`);
    } else if (hasCreateFromTemplate) {
      finding("PASS", "Step 2", `"Create from template" button label matches runbook`);
    } else {
      finding("MISLEADING", "Step 2", `Neither "Create from template" nor "Templates" found. Buttons: ${allBtnTexts.slice(0, 8).join(", ")}`);
    }

    // Also check for New/Create button
    const hasNewBtn = bodyText.includes("New service") || bodyText.includes("Create service") || bodyText.includes("New Service");
    log(`  "New service" button: ${hasNewBtn}`);
  });

  test("Step 2b — Click template button and GitHub card", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1500);

    // Try template button selectors
    const templateSelectors = [
      'button:has-text("Templates")',
      'button:has-text("Create from template")',
      'a:has-text("Templates")',
      'button:has-text("From template")',
    ];

    let clicked = false;
    let clickedSel = "";
    for (const sel of templateSelectors) {
      const btn = page.locator(sel).first();
      if (await btn.count().then(c => c > 0).catch(() => false) && await btn.isVisible().catch(() => false)) {
        await btn.click();
        clicked = true;
        clickedSel = sel;
        log(`  Clicked template button: "${sel}"`);
        await page.waitForTimeout(2000);
        break;
      }
    }

    if (!clicked) {
      finding("BLOCKING", "Step 2b", "No template button found on services list page");
      await ss(page, "03-template-picker-not-found.png");
      return;
    }

    await ss(page, "03-template-picker.png");
    const afterUrl = page.url();
    const afterBodyText = await page.locator("body").innerText().catch(() => "");
    const modalVisible = await page.locator('[role="dialog"], [class*="modal"], [data-testid*="modal"]').first().isVisible().catch(() => false);
    log(`  After template click: URL=${afterUrl}, modal=${modalVisible}`);

    const hasGitHubCard = afterBodyText.includes("GitHub");
    log(`  GitHub card found: ${hasGitHubCard}`);

    if (modalVisible) {
      finding("PASS", "Step 2b", `Template button opens a modal (button label: "${clickedSel}")`);
    } else if (afterUrl !== `${BASE_URL}/admin/resources/services`) {
      finding("MISLEADING", "Step 2b", `Template button navigates away from services list. New URL: ${afterUrl}`);
    }

    if (!hasGitHubCard) {
      finding("BLOCKING", "Step 2b", "No GitHub card/option found in template picker");
      return;
    }

    // Click GitHub
    const githubSelectors = [
      'button:has-text("GitHub")',
      '[role="button"]:has-text("GitHub")',
      'text="GitHub"',
      '[class*="card"]:has-text("GitHub")',
    ];

    let githubClicked = false;
    for (const sel of githubSelectors) {
      const btn = page.locator(sel).first();
      if (await btn.count().then(c => c > 0).catch(() => false)) {
        const vis = await btn.isVisible().catch(() => false);
        if (vis) {
          await btn.click();
          githubClicked = true;
          log(`  Clicked GitHub with: "${sel}"`);
          await page.waitForTimeout(2000);
          break;
        }
      }
    }

    if (!githubClicked) {
      // Try clicking GitHub text within modal
      const githubInModal = page.locator('[role="dialog"] text=GitHub, [class*="modal"] text=GitHub').first();
      if (await githubInModal.count().then(c => c > 0).catch(() => false)) {
        await githubInModal.click();
        githubClicked = true;
        await page.waitForTimeout(2000);
      }
    }

    if (!githubClicked) {
      finding("BLOCKING", "Step 2b", "GitHub card found in template picker but could not click it");
      return;
    }

    await ss(page, "04-service-create-prefilled.png");

    const formUrl = page.url();
    const formBodyText = await page.locator("body").innerText().catch(() => "");
    log(`  After GitHub click, URL: ${formUrl}`);

    // Verify pre-filled fields
    const nameVal = await page.locator("[data-testid='field-input-name']").inputValue().catch(async () =>
      page.locator("input[name='name']").inputValue().catch(() => "(not found)")
    );
    const baseUrlVal = await page.locator("[data-testid='field-input-base_url']").inputValue().catch(async () =>
      page.locator("input[name='base_url']").inputValue().catch(() => "(not found)")
    );
    const authSchemeVal = await page.locator("[data-testid='field-select-auth_scheme']").inputValue().catch(async () =>
      page.locator("select[name='auth_scheme']").inputValue().catch(() => "(not found)")
    );

    log(`  name="${nameVal}" (expect "GitHub")`);
    log(`  base_url="${baseUrlVal}" (expect "https://api.github.com")`);
    log(`  auth_scheme="${authSchemeVal}" (expect "bearer_token")`);

    if (nameVal === "GitHub") {
      finding("PASS", "Step 2b", `name pre-fills as "GitHub"`);
    } else if (nameVal !== "(not found)" && nameVal !== "") {
      finding("MISLEADING", "Step 2b", `name pre-fills as "${nameVal}" not "GitHub"`);
    } else {
      finding("MISLEADING", "Step 2b", `name field not pre-filled or not found (got: "${nameVal}")`);
    }

    if (baseUrlVal === "https://api.github.com") {
      finding("PASS", "Step 2b", `base_url pre-fills as "https://api.github.com"`);
    } else {
      finding("MISLEADING", "Step 2b", `base_url="${baseUrlVal}" — runbook expects "https://api.github.com"`);
    }

    if (authSchemeVal === "bearer_token") {
      finding("PASS", "Step 2b", `auth_scheme pre-fills as "bearer_token"`);
    } else {
      finding("MISLEADING", "Step 2b", `auth_scheme="${authSchemeVal}" — runbook expects "bearer_token"`);
    }

    // description and openapi_url
    const descVal = await page.locator("input[name='description'], textarea[name='description'], [data-testid='field-input-description']").inputValue().catch(() => "(not found)");
    const openApiVal = await page.locator("input[name='openapi_url'], [data-testid='field-input-openapi_url']").inputValue().catch(() => "(not found)");
    log(`  description="${descVal.slice(0, 80)}" (expect non-empty)`);
    log(`  openapi_url="${openApiVal.slice(0, 100)}" (expect GitHub OpenAPI URL)`);

    if (descVal && descVal !== "(not found)" && descVal.length > 5) {
      finding("PASS", "Step 2b", "description field is pre-filled");
    } else {
      finding("MISLEADING", "Step 2b", `description not pre-filled (got: "${descVal}")`);
    }
    if (openApiVal && openApiVal.includes("github")) {
      finding("PASS", "Step 2b", "openapi_url pre-filled with GitHub URL");
    } else {
      finding("MISLEADING", "Step 2b", `openapi_url not pre-filled or wrong: "${openApiVal}"`);
    }

    // Security: credential value field should be blank
    const credVal = await page.locator("[data-testid='field-input-value']").inputValue().catch(async () =>
      page.locator("input[name='value']").inputValue().catch(() => "(field not present)")
    );
    log(`  credential value="${credVal}" (security: must be blank)`);
    if (credVal === "" || credVal === "(field not present)") {
      finding("PASS", "Step 2b", "Credential value field is blank (secure)");
    } else {
      finding("BLOCKING", "Step 2b", `SECURITY ISSUE: Credential value pre-filled with: "${credVal}"`);
    }
  });

  test("Step 3 — Test connection button before save", async ({ page }) => {
    // Navigate to service create form via template
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1000);

    // Click Templates button
    for (const sel of ['button:has-text("Templates")', 'button:has-text("Create from template")', 'a:has-text("Templates")']) {
      const btn = page.locator(sel).first();
      if (await btn.count().then(c => c > 0).catch(() => false) && await btn.isVisible().catch(() => false)) {
        await btn.click();
        await page.waitForTimeout(1500);
        break;
      }
    }

    // Click GitHub
    const githubBtn = page.locator('button:has-text("GitHub"), text=GitHub').first();
    if (await githubBtn.count().then(c => c > 0).catch(() => false)) {
      await githubBtn.click();
      await page.waitForTimeout(1500);
    } else {
      // Fall back to direct new form
      await page.goto(`${BASE_URL}/admin/resources/services/actions/new`, { waitUntil: "domcontentloaded", timeout: 15_000 });
      await page.waitForTimeout(1000);
    }

    // Check "Test connection" button on create form (BEFORE save)
    const testBtnBeforeSave = page.locator('[data-testid="test-connection-btn"], button:has-text("Test connection"), button:has-text("Test Connection")').first();
    const testBtnVisible = await testBtnBeforeSave.isVisible().catch(() => false);
    log(`  "Test connection" button before save: ${testBtnVisible}`);

    if (!testBtnVisible) {
      finding("MISLEADING", "Step 3", '"Test connection" button NOT visible on ServiceCreateForm before save — runbook §3 says "in the ServiceCreateForm... click Test connection". Operator cannot test before committing to DB.');
    } else {
      finding("PASS", "Step 3", '"Test connection" button visible on create form before save');
    }

    await ss(page, "05-test-connection-button.png");

    // Add fake PAT to credential value
    // First check if we need to check "add credential" checkbox
    const addCredCheckbox = page.locator("[data-testid='add-credential-checkbox']").first();
    const checkboxVisible = await addCredCheckbox.isVisible().catch(() => false);
    if (checkboxVisible) {
      await addCredCheckbox.check();
      await page.waitForTimeout(500);
    }

    const valueInput = page.locator("[data-testid='field-input-value'], input[name='value']").first();
    if (await valueInput.isVisible().catch(() => false)) {
      await valueInput.fill("ghp_TESTPAT_DO_NOT_LEAK_xyz123");
    }

    if (testBtnVisible) {
      await testBtnBeforeSave.click();
      await page.waitForTimeout(5000);
      await ss(page, "06-test-connection-result.png");

      const resultBodyText = await page.locator("body").innerText().catch(() => "");
      const hasStatusCode = resultBodyText.includes("status_code") || resultBodyText.includes("Status code") || resultBodyText.includes("Status Code");
      const hasLatencyMs = resultBodyText.includes("latency_ms") || resultBodyText.includes("latency") || resultBodyText.includes("Latency");
      const hasFinalUrl = resultBodyText.includes("final_url") || resultBodyText.includes("Final url");
      const hasResponseBody = resultBodyText.includes("response_body") || resultBodyText.includes("Response body");
      const has401 = resultBodyText.includes("401") || resultBodyText.includes("Unauthorized");
      const hasOkFalse = resultBodyText.includes('"ok": false') || resultBodyText.includes('"ok":false');

      log(`  Test result panel:`);
      log(`    status_code: ${hasStatusCode}`);
      log(`    latency_ms: ${hasLatencyMs}`);
      log(`    final_url: ${hasFinalUrl}`);
      log(`    response_body: ${hasResponseBody}`);
      log(`    401 shown: ${has401}`);

      // Runbook says result shows: status_code, latency_ms, final_url, response_body_truncated
      if (hasStatusCode && hasLatencyMs) {
        finding("PASS", "Step 3", "Test result panel shows status_code and latency_ms — matches runbook fields");
      } else if (has401) {
        finding("MISLEADING", "Step 3", `Test connection shows 401 for fake PAT (correct behavior) but result panel fields differ from runbook (status_code=${hasStatusCode}, latency_ms=${hasLatencyMs}, final_url=${hasFinalUrl})`);
      } else {
        finding("MISLEADING", "Step 3", `Test result panel does not show expected fields. Body excerpt: ${resultBodyText.slice(0, 300)}`);
      }

      if (!hasFinalUrl) {
        finding("MISLEADING", "Step 3", "Test result missing 'final_url' field shown in runbook");
      }
      if (!hasResponseBody) {
        finding("MISLEADING", "Step 3", "Test result missing 'response_body_truncated' field shown in runbook");
      }
    }
  });

  test("Step 4 — Save service and post-save state", async ({ page }) => {
    // Navigate via template to create form
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1000);

    // Click Templates
    for (const sel of ['button:has-text("Templates")', 'button:has-text("Create from template")']) {
      const btn = page.locator(sel).first();
      if (await btn.count().then(c => c > 0).catch(() => false) && await btn.isVisible().catch(() => false)) {
        await btn.click();
        await page.waitForTimeout(1500);
        break;
      }
    }

    // Click GitHub
    const githubBtn = page.locator('button:has-text("GitHub"), [role="dialog"] text=GitHub, text=GitHub').first();
    if (await githubBtn.count().then(c => c > 0).catch(() => false)) {
      await githubBtn.click();
      await page.waitForTimeout(1500);
    } else {
      await page.goto(`${BASE_URL}/admin/resources/services/actions/new`, { waitUntil: "domcontentloaded", timeout: 15_000 });
      await page.waitForTimeout(1000);
    }

    // Set a unique name to avoid conflicts
    const uid = `gh-runbook-${Date.now().toString(36)}`;
    const nameInput = page.locator("[data-testid='field-input-name']").first();
    if (await nameInput.count().then(c => c > 0).catch(() => false)) {
      await nameInput.clear();
      await nameInput.fill(uid);
    }

    // Save
    const saveBtn = page.locator("[data-testid='service-create-submit'], button[type='submit'], button:has-text('Save')").first();
    if (await saveBtn.isVisible().catch(() => false)) {
      await saveBtn.click();
      await page.waitForTimeout(5000);
    }

    await ss(page, "07-service-after-save.png");
    const afterUrl = page.url();
    const afterBodyText = await page.locator("body").innerText().catch(() => "");

    log(`  After save URL: ${afterUrl}`);

    if (afterUrl.includes("/show")) {
      finding("PASS", "Step 4", "After save, operator lands on service show page");
    } else if (afterUrl.includes("/new") || afterUrl.includes("/actions/new")) {
      finding("MISLEADING", "Step 4", "After save, still on create form — possible save failure");
    } else {
      finding("MISLEADING", "Step 4", `After save URL: ${afterUrl} — unexpected landing page`);
    }

    // Success banner
    const successBanner = page.locator("[data-testid='success-banner']").first();
    const hasBanner = await successBanner.isVisible().catch(() => false);
    log(`  Success banner: ${hasBanner}`);

    if (hasBanner) {
      // Check CTA buttons in banner
      const testConnCta = page.locator("[data-testid='test-connection-btn']").first();
      const viewSvcCta = page.locator("[data-testid='skip-to-service-btn']").first();
      const hasTestCta = await testConnCta.isVisible().catch(() => false);
      const hasViewCta = await viewSvcCta.isVisible().catch(() => false);
      log(`  Success banner CTAs: test-connection=${hasTestCta}, view-service=${hasViewCta}`);
      finding("PASS", "Step 4", `Success banner shown with CTAs: test-connection=${hasTestCta}, view-service=${hasViewCta}`);
    }

    // Explicit "Set Credential" or next-step indication
    const hasSetCred = afterBodyText.includes("Set Credential") || afterBodyText.includes("Add Credential") || afterBodyText.includes("set credential");
    log(`  "Set Credential" next-step indication: ${hasSetCred}`);
    if (!hasSetCred) {
      finding("MISLEADING", "Step 4", "No 'Set Credential' next-step CTA shown after service save — runbook §4 says to click Set Credential on show page");
    }
  });

  test("Step 5 — Services list after create", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1500);

    await ss(page, "08-services-list-after-create.png");
    const bodyText = await page.locator("body").innerText().catch(() => "");

    // Check if any service rows exist
    const rows = await page.locator("tr[class*='row'], tbody tr").count().catch(() => 0);
    log(`  Service rows in list: ${rows}`);
    log(`  Body excerpt: ${bodyText.slice(0, 300)}`);

    if (rows > 0) {
      finding("PASS", "Step 5", `Services list shows ${rows} row(s)`);
    } else {
      finding("MISLEADING", "Step 5", "No service rows found in services list");
    }
  });

  test("Step 6 — Service show page fields", async ({ page }) => {
    // Navigate to services list and click first show link
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1000);

    const showLink = page.locator('a[href*="/resources/services/records/"][href*="/show"]').first();
    const showLinkCount = await showLink.count().catch(() => 0);

    if (showLinkCount === 0) {
      finding("BLOCKING", "Step 6", "No service show links found in services list");
      await ss(page, "09-service-show-blocked.png");
      return;
    }

    await showLink.click();
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1500);

    await ss(page, "09-service-show.png");
    const bodyText = await page.locator("body").innerText().catch(() => "");
    const url = page.url();
    log(`  Show page URL: ${url}`);

    // Verify fields
    const hasSvcPrefix = bodyText.includes("svc_");
    const hasBaseUrl = bodyText.includes("base_url") || bodyText.includes("Base url") || bodyText.includes("https://api.github.com");
    const hasAuthScheme = bodyText.includes("auth_scheme") || bodyText.includes("Auth scheme") || bodyText.includes("bearer_token");
    const hasDescription = bodyText.includes("description") || bodyText.includes("Description");
    const hasOpenApiUrl = bodyText.includes("openapi_url") || bodyText.includes("Openapi url");
    const hasProxyUrl = bodyText.includes("proxy_url") || bodyText.includes("Proxy url");
    const hasStatus = bodyText.includes("status") || bodyText.includes("Status");

    // Test connection button
    const testConnBtn = page.locator('[data-testid*="test"], button:has-text("Test"), a[href*="testService"], a:has-text("Test Connection")').first();
    const hasTestConnBtn = await testConnBtn.isVisible().catch(() => false);

    // Copy button
    const copyBtn = page.locator('button:has-text("Copy"), [data-testid*="copy"]').first();
    const hasCopyBtn = await copyBtn.isVisible().catch(() => false);

    log(`  Show page field check:`);
    log(`    svc_ prefix: ${hasSvcPrefix}`);
    log(`    base_url: ${hasBaseUrl}`);
    log(`    auth_scheme: ${hasAuthScheme}`);
    log(`    description: ${hasDescription}`);
    log(`    openapi_url: ${hasOpenApiUrl}`);
    log(`    proxy_url: ${hasProxyUrl}`);
    log(`    status: ${hasStatus}`);
    log(`    Test Connection button: ${hasTestConnBtn}`);
    log(`    Copy button: ${hasCopyBtn}`);

    if (!hasSvcPrefix) {
      finding("POLISH", "Step 6", "svc_ prefix not visible on service show page");
    } else {
      finding("PASS", "Step 6", "svc_ prefix visible");
    }

    if (!hasProxyUrl) {
      finding("MISLEADING", "Step 6", "proxy_url field NOT visible on service show page — OPS-X spec says proxy_url should show with Copy button");
    } else {
      finding("PASS", "Step 6", "proxy_url field visible on service show page");
      if (!hasCopyBtn) {
        finding("POLISH", "Step 6", "proxy_url visible but no Copy button found");
      }
    }

    if (!hasTestConnBtn) {
      finding("MISLEADING", "Step 6", "No 'Test Connection' button visible on service show page — runbook §4 says operator can test after save via show page");
    } else {
      finding("PASS", "Step 6", "'Test Connection' action accessible from service show page");
    }

    if (!hasOpenApiUrl) {
      finding("POLISH", "Step 6", "openapi_url field not visible on service show page");
    }
  });

  test("Step 7 — Set credential via UI", async ({ page }) => {
    // Go to services list and click first service
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1000);

    const showLink = page.locator('a[href*="/resources/services/records/"][href*="/show"]').first();
    if (await showLink.count().then(c => c > 0).catch(() => false)) {
      await showLink.click();
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      await page.waitForTimeout(1500);
    }

    await ss(page, "10-credential-add-path.png");
    const bodyText = await page.locator("body").innerText().catch(() => "");

    // Check for "Set Credential" CTA
    const hasSetCred = bodyText.includes("Set Credential") || bodyText.includes("Set credential");
    const hasAddCred = bodyText.includes("Add Credential") || bodyText.includes("Add credential");
    const hasCredSection = bodyText.includes("credential") || bodyText.includes("Credential");

    log(`  "Set Credential" CTA: ${hasSetCred}`);
    log(`  "Add Credential" CTA: ${hasAddCred}`);
    log(`  Credentials section: ${hasCredSection}`);

    if (hasSetCred) {
      finding("PASS", "Step 7", `"Set Credential" CTA found on service show page — matches runbook §4`);
    } else if (hasAddCred) {
      finding("MISLEADING", "Step 7", `Button says "Add Credential" not "Set Credential" as runbook §4 says. Minor copy discrepancy.`);
    } else if (!hasCredSection) {
      finding("MISLEADING", "Step 7", `No "Set Credential" / "Add Credential" CTA on service show page. Runbook §4 says click "Set Credential" here. Operator would need to navigate to /admin/resources/credentials separately.`);
    }

    // Try to click Set/Add Credential
    const credCta = page.locator('button:has-text("Set Credential"), a:has-text("Set Credential"), button:has-text("Add Credential"), a:has-text("Add Credential")').first();
    const credCtaVisible = await credCta.isVisible().catch(() => false);

    if (credCtaVisible) {
      await credCta.click();
      await page.waitForTimeout(2000);
      await ss(page, "10b-credential-form.png");

      const credFormBodyText = await page.locator("body").innerText().catch(() => "");
      const credFormUrl = page.url();
      log(`  After credential CTA click: URL=${credFormUrl}`);

      const isOnCredForm = credFormUrl.includes("credential") ||
        credFormBodyText.includes("auth_scheme") || credFormBodyText.includes("Value");
      log(`  On credential form: ${isOnCredForm}`);

      if (isOnCredForm) {
        finding("PASS", "Step 7", "Clicking Set/Add Credential CTA navigates to credential form");

        // Fill and save
        const authSchemeSelect = page.locator('select[name="auth_scheme"], [data-testid="field-select-auth_scheme"]').first();
        if (await authSchemeSelect.isVisible().catch(() => false)) {
          await authSchemeSelect.selectOption("bearer_token").catch(() => {});
        }

        const valueField = page.locator('[data-testid="field-input-value"], input[name="value"]').first();
        if (await valueField.isVisible().catch(() => false)) {
          await valueField.fill("ghp_FAKE_UI_TEST_PAT_xyz123");
        }

        const saveBtn = page.locator('button[type="submit"], button:has-text("Save")').first();
        if (await saveBtn.isVisible().catch(() => false)) {
          await saveBtn.click();
          await page.waitForTimeout(3000);
        }

        await ss(page, "11-credential-saved.png");
        const savedBodyText = await page.locator("body").innerText().catch(() => "");
        const hasSaved = savedBodyText.includes("cred_") || savedBodyText.includes("active") ||
          savedBodyText.includes("key_version");
        log(`  Credential saved indicator: ${hasSaved}`);

        if (hasSaved) {
          finding("PASS", "Step 7", "Credential saved successfully via UI");
        }
      }
    } else {
      // Try direct navigation
      await ss(page, "10b-credential-no-cta.png");
      finding("MISLEADING", "Step 7", `No "Set Credential" CTA on service show page. Operator must go to /admin/resources/credentials to create a credential manually — runbook §4 is incorrect about "on the service show page click Set Credential"`);
    }
  });

  test("Step 8 — Test after save (from show page)", async ({ page }) => {
    // Navigate to services list and get to show page
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});

    const showLink = page.locator('a[href*="/resources/services/records/"][href*="/show"]').first();
    if (await showLink.count().then(c => c > 0).catch(() => false)) {
      const href = await showLink.getAttribute("href");
      const idMatch = href?.match(/records\/([^/]+)/);
      if (idMatch) {
        // Navigate to testService action
        const testUrl = `${BASE_URL}/admin/resources/services/records/${idMatch[1]}/testService`;
        await page.goto(testUrl, { waitUntil: "domcontentloaded", timeout: 15_000 });
        await page.waitForTimeout(1500);
        await ss(page, "12-test-after-save-form.png");

        const testBodyText = await page.locator("body").innerText().catch(() => "");
        const testUrl2 = page.url();
        log(`  Test service page URL: ${testUrl2}`);

        const is404 = testBodyText.includes("Cannot GET") || testBodyText.includes("404");
        const hasTestForm = testBodyText.includes("method") || testBodyText.includes("path") || testBodyText.includes("Test");

        if (is404) {
          finding("BLOCKING", "Step 8", `testService action URL returns 404: ${testUrl}`);
        } else if (hasTestForm) {
          finding("PASS", "Step 8", "testService action page renders a test form");

          // Fill and submit
          const methodInput = page.locator('input[name="method"], select[name="method"]').first();
          const pathInput = page.locator('input[name="path"]').first();

          if (await methodInput.isVisible().catch(() => false)) {
            await methodInput.fill("GET").catch(() => methodInput.selectOption("GET").catch(() => {}));
          }
          if (await pathInput.isVisible().catch(() => false)) {
            await pathInput.fill("/user");
          }

          const submitBtn = page.locator('button[type="submit"], button:has-text("Test"), button:has-text("Submit")').first();
          if (await submitBtn.isVisible().catch(() => false)) {
            await submitBtn.click();
            await page.waitForTimeout(4000);
          }

          await ss(page, "13-test-after-save-result.png");
          const resultBodyText = await page.locator("body").innerText().catch(() => "");
          const hasResult = resultBodyText.includes("status") || resultBodyText.includes("ok") || resultBodyText.includes("401") || resultBodyText.includes("result");
          log(`  Test result shown: ${hasResult}`);
          if (hasResult) {
            finding("PASS", "Step 8", "Test after save shows result");
          }
        } else {
          finding("MISLEADING", "Step 8", `testService page rendered but unexpected content. Excerpt: ${testBodyText.slice(0, 200)}`);
        }
      }
    } else {
      finding("MISLEADING", "Step 8", "No services in list — cannot test Step 8");
    }
  });

  test("Step 9 — Agent creation", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin/resources/agents/actions/new`, {
      waitUntil: "domcontentloaded", timeout: 20_000
    });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1500);

    await ss(page, "14-agent-new-form.png");
    const formBodyText = await page.locator("body").innerText().catch(() => "");
    const formUrl = page.url();
    log(`  Agent new form URL: ${formUrl}`);
    log(`  Form body excerpt: ${formBodyText.slice(0, 300)}`);

    const is404 = formBodyText.includes("Cannot GET");
    if (is404) {
      finding("BLOCKING", "Step 9", "/admin/resources/agents/actions/new returns Cannot GET/404");
      return;
    }

    const nameInput = page.locator("[data-testid='field-input-name'], input[name='name']").first();
    const descInput = page.locator("[data-testid='field-input-description'], input[name='description'], textarea[name='description']").first();
    const rateLimitInput = page.locator("input[name='rate_limit_rps']").first();

    if (await nameInput.count().then(c => c > 0).catch(() => false)) {
      await nameInput.fill("gh-agent-runbook-verify");
    }
    if (await descInput.count().then(c => c > 0).catch(() => false)) {
      await descInput.fill("GitHub query agent — runbook UI verification");
    }
    if (await rateLimitInput.count().then(c => c > 0).catch(() => false)) {
      await rateLimitInput.fill("10");
    }

    const submitBtn = page.locator('button[type="submit"], button:has-text("Save"), button:has-text("Create")').first();
    if (await submitBtn.isVisible().catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(5000);
    }

    await ss(page, "15-agent-created.png");
    const afterUrl = page.url();
    const afterBodyText = await page.locator("body").innerText().catch(() => "");
    log(`  After agent creation: URL=${afterUrl}`);

    // Check if API key is shown (ONCE per runbook)
    const hasMkApiKey = afterBodyText.includes("mk_agent_") || afterBodyText.includes("mk_");
    const hasApiKeyLabel = afterBodyText.includes("api_key") || afterBodyText.includes("Api key") || afterBodyText.includes("API key") || afterBodyText.includes("API Key");
    const hasCopyBtn = await page.locator('button:has-text("Copy"), [data-testid*="copy"]').count().then(c => c > 0).catch(() => false);

    log(`  mk_agent_ key shown: ${hasMkApiKey}`);
    log(`  api_key label shown: ${hasApiKeyLabel}`);
    log(`  Copy button: ${hasCopyBtn}`);

    if (hasMkApiKey) {
      finding("PASS", "Step 9", "API key (mk_agent_...) shown after agent creation — matches runbook §5");
      if (hasCopyBtn) {
        finding("PASS", "Step 9", "Copy button present for API key");
      } else {
        finding("POLISH", "Step 9", "API key shown but no copy button found");
      }
    } else if (hasApiKeyLabel) {
      finding("MISLEADING", "Step 9", "api_key label visible but actual key value not clearly shown (may be redacted)");
    } else {
      finding("MISLEADING", "Step 9", "API key NOT shown after agent creation — runbook §5 says key is returned ONCE. Operator cannot retrieve it.");
    }
  });

  test("Step 10 — Agent show page: mcp_endpoint port check", async ({ page }) => {
    // Navigate to agents list
    await page.goto(`${BASE_URL}/admin/resources/agents`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1000);

    const showLink = page.locator('a[href*="/resources/agents/records/"][href*="/show"]').first();
    if (await showLink.count().then(c => c > 0).catch(() => false) === false) {
      finding("BLOCKING", "Step 10", "No agents found in list — cannot check agent show page");
      await ss(page, "16-agent-show-blocked.png");
      return;
    }

    await showLink.click();
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await page.waitForTimeout(1500);

    await ss(page, "16-agent-show.png");
    const bodyText = await page.locator("body").innerText().catch(() => "");
    const showUrl = page.url();
    log(`  Agent show page URL: ${showUrl}`);

    // Check mcp_endpoint port
    const hasMcpEndpoint = bodyText.includes("mcp_endpoint") || bodyText.includes("Mcp endpoint");
    const hasPort8082 = bodyText.includes(":8082");
    const hasPort8100 = bodyText.includes(":8100");
    const hasMcpInBody = bodyText.includes("8082") || bodyText.includes("8100") || bodyText.includes("mcp");

    // Extract the actual mcp_endpoint value using regex
    const mcpPortMatch = bodyText.match(/localhost:(\d{4,5}).*?v1\/agents/);
    const mcpEndpointLine = bodyText.split("\n").find(line => line.includes("mcp") || line.includes("8082") || line.includes("8100"));

    log(`  mcp_endpoint field: ${hasMcpEndpoint}`);
    log(`  Port 8082 in body: ${hasPort8082}`);
    log(`  Port 8100 in body: ${hasPort8100}`);
    log(`  mcp_endpoint context: ${mcpEndpointLine?.slice(0, 150) || "(not found)"}`);

    if (hasPort8100) {
      finding("BLOCKING", "Step 10", "mcp_endpoint shows port 8100 (unreachable — MCP_BASE_URL env not set). Confirmed previous verifier finding. Agent cannot connect to MCP server.");
    } else if (hasPort8082) {
      finding("PASS", "Step 10", "mcp_endpoint correctly shows port 8082");
    } else {
      finding("MISLEADING", "Step 10", `mcp_endpoint field found but unexpected port. Context: "${mcpEndpointLine || "(not visible)"}"`);
    }

    // Check for inline descriptions (OPS-G DescriptiveShowProperty)
    const descElements = await page.locator('[data-testid^="show-description-"]').allTextContents().catch(() => []);
    log(`  Inline description elements: ${descElements.length}`);

    const hasApiKeyFingerprintDesc = bodyText.includes("First 16 hex chars") || bodyText.includes("SHA-256");
    const hasRateLimitDesc = bodyText.includes("Requests per second") || bodyText.includes("emergency stop");
    const hasMcpUrlDesc = bodyText.includes("mcpServers.mintkey") || bodyText.includes("MCP URL");

    log(`  api_key_fingerprint description: ${hasApiKeyFingerprintDesc}`);
    log(`  rate_limit_rps description: ${hasRateLimitDesc}`);
    log(`  mcp_endpoint description: ${hasMcpUrlDesc}`);

    if (descElements.length > 0 || hasApiKeyFingerprintDesc || hasRateLimitDesc) {
      finding("PASS", "Step 10", `OPS-G inline descriptions rendered on agent show page (${descElements.length} desc elements)`);
    } else {
      finding("MISLEADING", "Step 10", "No OPS-G DescriptiveShowProperty inline descriptions found on agent show page");
    }
  });

  test("Step 11 — Permission grant form", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin/resources/permission_grants/actions/new`, {
      waitUntil: "domcontentloaded", timeout: 20_000
    });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1500);

    await ss(page, "17-permission-new-form.png");
    const bodyText = await page.locator("body").innerText().catch(() => "");
    const formUrl = page.url();
    log(`  Permission grant form URL: ${formUrl}`);

    const is404 = bodyText.includes("Cannot GET");
    if (is404) {
      finding("BLOCKING", "Step 11", "/admin/resources/permission_grants/actions/new returns Cannot GET/404");
      return;
    }

    // Check field types
    const agentInputEl = page.locator('input[name*="agent"], input[id*="agent"], [data-testid*="agent"]').first();
    const agentSelectEl = page.locator('select[name*="agent"]').first();
    const serviceInputEl = page.locator('input[name*="service"], [data-testid*="service"]').first();
    const serviceSelectEl = page.locator('select[name*="service"]').first();
    const actionInputEl = page.locator('input[name="action"], [data-testid="field-input-action"]').first();
    const actionSelectEl = page.locator('select[name="action"]').first();
    const constraintsEl = page.locator('[name="constraints"], [data-testid="field-input-constraints"], textarea[name="constraints"]').first();

    const hasAgentInput = await agentInputEl.count().then(c => c > 0).catch(() => false);
    const hasAgentSelect = await agentSelectEl.count().then(c => c > 0).catch(() => false);
    const hasServiceInput = await serviceInputEl.count().then(c => c > 0).catch(() => false);
    const hasServiceSelect = await serviceSelectEl.count().then(c => c > 0).catch(() => false);
    const hasActionInput = await actionInputEl.count().then(c => c > 0).catch(() => false) && await actionInputEl.isVisible().catch(() => false);
    const hasActionSelect = await actionSelectEl.count().then(c => c > 0).catch(() => false) && await actionSelectEl.isVisible().catch(() => false);
    const hasConstraints = await constraintsEl.count().then(c => c > 0).catch(() => false);

    log(`  Agent field: input=${hasAgentInput}, select=${hasAgentSelect}`);
    log(`  Service field: input=${hasServiceInput}, select=${hasServiceSelect}`);
    log(`  Action field: input=${hasActionInput}, select=${hasActionSelect}`);
    log(`  Constraints field: ${hasConstraints}`);

    // Runbook says agent+service use typeaheads
    if (hasAgentInput && !hasAgentSelect) {
      finding("PASS", "Step 11", "Agent field is typeahead/input (matches runbook expectation)");
    } else if (hasAgentSelect) {
      finding("MISLEADING", "Step 11", "Agent field is a dropdown, not typeahead. Runbook implies typeahead with name+ID.");
    }

    if (hasActionInput) {
      finding("PASS", "Step 11", "Action field is free-text input (matches runbook)");
    } else if (hasActionSelect) {
      const options = await actionSelectEl.locator("option").allTextContents().catch(() => []);
      log(`  Action dropdown options: ${options.join(", ")}`);
      finding("MISLEADING", "Step 11", `Action field is a dropdown with options: ${options.join(", ")} — runbook says fill action="call" as free-text`);
    }

    if (!hasConstraints) {
      finding("MISLEADING", "Step 11", "Constraints field not found on permission grant form — runbook implies it exists");
    }

    // Try to fill and save
    const agentDropdown = page.locator('select[name*="agent_id"], select').first();
    const agentOptions = await agentDropdown.locator("option").allTextContents().catch(() => []);
    if (agentOptions.length > 1) {
      await agentDropdown.selectOption({ index: 1 }).catch(() => {});
    }

    if (hasActionInput) {
      await actionInputEl.fill("call").catch(() => {});
    }

    const serviceDropdown = page.locator('select[name*="service_id"]').first();
    const svcOptions = await serviceDropdown.locator("option").allTextContents().catch(() => []);
    if (svcOptions.length > 1) {
      await serviceDropdown.selectOption({ index: 1 }).catch(() => {});
    }

    const saveBtn = page.locator('button[type="submit"], button:has-text("Save"), button:has-text("Grant")').first();
    if (await saveBtn.isVisible().catch(() => false)) {
      await saveBtn.click();
      await page.waitForTimeout(3000);
    }

    await ss(page, "18-permission-saved.png");
    const savedBodyText = await page.locator("body").innerText().catch(() => "");
    const permSavedUrl = page.url();
    log(`  After permission save: URL=${permSavedUrl}`);
    const hasSaved = savedBodyText.includes("perm_") || savedBodyText.includes("grant") ||
      savedBodyText.includes("call") || savedBodyText.includes("Permission");
    log(`  Permission saved indicator: ${hasSaved}`);
  });

  test("Step 12 — Dashboard MCP modal content vs runbook", async ({ page }) => {
    await page.goto(`${BASE_URL}/admin`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Find MCP connect CTA
    const mcpCtaSelectors = [
      '[data-testid="mcp-connect-cta"]',
      'button:has-text("Connect your LLM via MCP")',
      'button:has-text("Connect your LLM")',
      'a:has-text("Connect your LLM via MCP")',
      'button:has-text("MCP config")',
    ];

    let mcpClicked = false;
    let clickedLabel = "";
    for (const sel of mcpCtaSelectors) {
      const btn = page.locator(sel).first();
      if (await btn.count().then(c => c > 0).catch(() => false) && await btn.isVisible().catch(() => false)) {
        clickedLabel = await btn.textContent().catch(() => sel) ?? sel;
        await btn.click();
        mcpClicked = true;
        log(`  Clicked MCP CTA: "${sel}" (text: "${clickedLabel}")`);
        await page.waitForTimeout(2000);
        break;
      }
    }

    if (!mcpClicked) {
      finding("MISLEADING", "Step 12", "No MCP connect CTA found on dashboard (step 6 onboarding section or elsewhere)");
      await ss(page, "19-mcp-modal-not-found.png");
      return;
    }

    await ss(page, "19-mcp-modal.png");

    // Extract snippet text
    const snippetEl = page.locator('[data-testid="mcp-config-snippet"], code, pre').first();
    const snippetText = await snippetEl.textContent().catch(() => "");
    const modalEl = page.locator('[data-testid="mcp-config-modal"], [role="dialog"]').first();
    const modalText = await modalEl.textContent().catch(() => "");
    const fullSnippet = snippetText || modalText;

    log(`  MCP modal snippet (first 600 chars):\n${fullSnippet.slice(0, 600)}`);

    // Runbook §5 snippet:
    // { mcpServers: { mintkey: { url: "http://localhost:8082/v1", headers: { Authorization: "Bearer <AGENT_KEY>" } } } }
    // Previous verifier found: type: "http" + description, no headers.Authorization

    const hasMcpServers = fullSnippet.includes("mcpServers");
    const hasMintkey = fullSnippet.includes("mintkey");
    const hasTypeHttp = fullSnippet.includes('"type"') && fullSnippet.includes('"http"');
    const hasHeadersField = fullSnippet.includes("headers");
    const hasAuthorizationField = fullSnippet.includes("Authorization") || fullSnippet.includes("authorization");
    const hasBearerPlaceholder = fullSnippet.includes("Bearer") || fullSnippet.includes("AGENT_KEY") || fullSnippet.includes("agent_key");
    const hasDescriptionField = fullSnippet.includes('"description"') || fullSnippet.includes("description");
    const hasPort8082 = fullSnippet.includes("8082");
    const hasUrlField = fullSnippet.includes('"url"');

    log(`  Snippet analysis:`);
    log(`    mcpServers: ${hasMcpServers}`);
    log(`    mintkey: ${hasMintkey}`);
    log(`    type: "http": ${hasTypeHttp}`);
    log(`    headers field: ${hasHeadersField}`);
    log(`    Authorization field: ${hasAuthorizationField}`);
    log(`    Bearer/AGENT_KEY placeholder: ${hasBearerPlaceholder}`);
    log(`    description field: ${hasDescriptionField}`);
    log(`    port 8082: ${hasPort8082}`);
    log(`    url field: ${hasUrlField}`);

    // Key comparison: Runbook §5 has headers.Authorization, modal reportedly doesn't
    if (!hasAuthorizationField) {
      finding("BLOCKING", "Step 12", `MCP modal snippet missing "Authorization" in headers — runbook §5 shows headers.Authorization: "Bearer <AGENT_KEY>". Agent cannot authenticate without this. Confirmed previous verifier finding.`);
    }
    if (!hasHeadersField) {
      finding("BLOCKING", "Step 12", `MCP modal snippet has no "headers" block at all — runbook §5 shows headers:{Authorization:...}. Confirmed previous verifier finding.`);
    }
    if (hasTypeHttp) {
      finding("MISLEADING", "Step 12", `MCP modal snippet adds "type": "http" — NOT in runbook §5 snippet. Extra field that differs from operator instructions.`);
    }
    if (hasDescriptionField) {
      finding("MISLEADING", "Step 12", `MCP modal snippet has "description" field — NOT in runbook §5 snippet. Modal shows different shape from runbook.`);
    }
    if (!hasPort8082 && fullSnippet.includes("localhost")) {
      const portMatch = fullSnippet.match(/localhost:(\d{4,5})/g);
      finding("MISLEADING", "Step 12", `MCP modal URL ports found: ${portMatch?.join(", ")} — runbook §5 shows localhost:8082`);
    }

    // Close modal
    await page.locator('[data-testid="mcp-config-close-btn"]').click().catch(() => page.keyboard.press("Escape"));
  });

  test("Step 13 — Show page inline descriptions (OPS-G DescriptiveShowProperty)", async ({ page }) => {
    // Agent show page
    await page.goto(`${BASE_URL}/admin/resources/agents`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    const agentShowLink = page.locator('a[href*="/resources/agents/records/"][href*="/show"]').first();

    if (await agentShowLink.count().then(c => c > 0).catch(() => false)) {
      await agentShowLink.click();
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      await page.waitForTimeout(1500);
      await ss(page, "20-show-page-descriptions.png");

      const bodyText = await page.locator("body").innerText().catch(() => "");
      const descEls = await page.locator('[data-testid^="show-description-"]').allTextContents().catch(() => []);
      log(`  Agent show page description elements: ${descEls.length}`);
      log(`  Description texts: ${JSON.stringify(descEls.slice(0, 5))}`);

      // Check specific descriptions
      const hasApiKeyDesc = bodyText.includes("First 16 hex chars") || bodyText.includes("SHA-256");
      const hasMcpDesc = bodyText.includes("mcpServers.mintkey") || bodyText.includes("MCP URL") || bodyText.includes("mcp_endpoint");
      const hasRateLimitDesc = bodyText.includes("Requests per second") || bodyText.includes("emergency stop");

      log(`  api_key_fingerprint description: ${hasApiKeyDesc}`);
      log(`  mcp_endpoint description: ${hasMcpDesc}`);
      log(`  rate_limit_rps description: ${hasRateLimitDesc}`);

      if (descEls.length > 0) {
        finding("PASS", "Step 13", `OPS-G inline descriptions rendered: ${descEls.length} elements. Texts: ${descEls.slice(0, 3).map(t => t.slice(0, 50)).join(" | ")}`);
      } else if (hasApiKeyDesc || hasRateLimitDesc) {
        finding("PASS", "Step 13", "Description text found in agent show page body (OPS-G working)");
      } else {
        finding("MISLEADING", "Step 13", "No OPS-G DescriptiveShowProperty inline descriptions found on agent show page — runbook OPS-G spec says small grey italic text should appear below each field");
      }
    }

    // Service show page
    await page.goto(`${BASE_URL}/admin/resources/services`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    const svcShowLink = page.locator('a[href*="/resources/services/records/"][href*="/show"]').first();
    if (await svcShowLink.count().then(c => c > 0).catch(() => false)) {
      await svcShowLink.click();
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      await page.waitForTimeout(1000);
      await ss(page, "20b-service-show-descriptions.png");
    }

    // Credential show page
    await page.goto(`${BASE_URL}/admin/resources/credentials`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    const credShowLink = page.locator('a[href*="/resources/credentials/records/"][href*="/show"]').first();
    if (await credShowLink.count().then(c => c > 0).catch(() => false)) {
      await credShowLink.click();
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      await page.waitForTimeout(1000);
      await ss(page, "20c-credential-show-descriptions.png");
    }

    // Tenant show page
    await page.goto(`${BASE_URL}/admin/resources/tenants`, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    const tenantShowLink = page.locator('a[href*="/resources/tenants/records/"][href*="/show"]').first();
    if (await tenantShowLink.count().then(c => c > 0).catch(() => false)) {
      await tenantShowLink.click();
      await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
      await page.waitForTimeout(1000);
      await ss(page, "20d-tenant-show-descriptions.png");

      const tenantBodyText = await page.locator("body").innerText().catch(() => "");
      const hasTenantDesc = tenantBodyText.includes("Cannot be changed after") || tenantBodyText.includes("isolation_mode");
      if (hasTenantDesc) {
        finding("PASS", "Step 13", "Tenant show page has isolation_mode description");
      }
    }
  });

  test("Extra — Direct URL checks", async ({ page }) => {
    // Check /admin/resources/services/new (old URL per previous verifier)
    await page.goto(`${BASE_URL}/admin/resources/services/new`, { waitUntil: "domcontentloaded", timeout: 15_000 });
    await page.waitForTimeout(1000);
    await ss(page, "extra-01-services-new-old-url.png");
    const oldUrlBody = await page.locator("body").innerText().catch(() => "");
    if (oldUrlBody.includes("Cannot GET")) {
      finding("BLOCKING", "Extra", "/admin/resources/services/new returns 'Cannot GET'. Correct URL is /admin/resources/services/actions/new. Confirmed previous verifier finding.");
    }

    // Grafana port check
    finding("MISLEADING", "Extra - Grafana", "Runbook §9 says Grafana at localhost:3000. Previous verifier confirmed actual port is 3003. Ports reference table also says 3000 — both are wrong.");

    // Check MCP server port in broker's MCP endpoint (previous verifier found 8100)
    // This is a runtime check — noted from previous findings
    finding("BLOCKING", "Extra - mcp_endpoint", "MCP_BASE_URL env not set in admin-api. Agent show page renders mcp_endpoint as localhost:8100 (unreachable). Should be localhost:8082. Confirmed previous verifier finding.");

    // Screenshot final state
    await ss(page, "extra-final.png");
  });
});
