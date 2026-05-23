import { test } from "@playwright/test";

const RES = ["services", "agents", "permission_grants", "service_api_keys", "credentials", "audit_events", "tenants"];

for (const r of RES) {
  test(`DIAGNOSE list ${r}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto(`/admin/resources/${r}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const body = await page.locator("body").innerText();
    const hasErr = body.includes("Javascript Error") || body.includes("JavaScript Error") || errors.length > 0;
    console.log(`[${r}] hasErr=${hasErr} bodyHead=${body.slice(0, 300).replace(/\n/g, " | ")}`);
    if (errors.length) console.log(`[${r}] JS ERRORS: ${errors.join(" ;; ")}`);
  });
}

for (const r of ["services", "agents", "permission_grants", "service_api_keys", "tenants"]) {
  test(`DIAGNOSE new ${r}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto(`/admin/resources/${r}/actions/new`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1500);
    const body = await page.locator("body").innerText();
    const hasErr = body.includes("avascript Error") || body.includes("Something went wrong") || errors.length > 0;
    console.log(`[NEW ${r}] hasErr=${hasErr} bodyHead=${body.slice(0, 400).replace(/\n/g, " | ")}`);
    if (errors.length) console.log(`[NEW ${r}] JS ERRORS: ${errors.join(" ;; ")}`);
  });
}

test("DIAGNOSE submit tenants new", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto("/admin/resources/tenants/actions/new", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  // fill the form
  const inputs = page.locator("section[data-css] input, form input");
  console.log("input count:", await inputs.count());
  const slug = page.locator('input[name="slug"], input').first();
  await slug.fill("diag-test-tenant-x");
  // there is a display_name input
  const all = await page.locator("input").all();
  for (const i of all) { const n = await i.getAttribute("name"); console.log("input name:", n); }
  // pick by label proximity is hard; just fill display_name if it exists
  const dn = page.locator('input').nth(1);
  await dn.fill("Diag Test Tenant X");
  await page.getByRole("button", { name: /save/i }).click();
  await page.waitForTimeout(2500);
  const body = await page.locator("body").innerText();
  console.log("=== AFTER SUBMIT BODY ===\n", body.slice(0, 1500));
  console.log("=== JS ERRORS ===\n", errors.join("\n"));
  await page.screenshot({ path: "test-results/diag-after-submit.png", fullPage: true });
});
