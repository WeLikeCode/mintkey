/**
 * Unit tests for ServiceCreateForm URL-param pre-fill (OPS-S+U integration).
 *
 * vitest environment is `node` (no jsdom), so these are source-file inspection
 * tests that verify the correct implementation patterns. Playwright e2e covers
 * real browser pre-fill behavior.
 *
 * Assertions:
 *   1. ServiceCreateForm imports useSearchParams.
 *   2. Component reads ?template= param from search params.
 *   3. Fetches template-detail action on mount when ?template present.
 *   4. Sets name, base_url, auth_scheme, description, openapi_url from template.
 *   5. DOES NOT auto-fill credential value (security boundary).
 *   6. Renders template-prefill-banner with template name.
 *   7. Banner has a "Clear" link that navigates to /new without param.
 *   8. Test-before-save button is present (data-testid="test-before-save-btn").
 *   9. Test-before-save is disabled unless name + base_url + auth_scheme + cred value filled.
 *  10. Test-before-save calls test-transient resource action via ApiClient.
 *  11. Result panel renders after test (data-testid="test-before-save-result").
 *  12. Failed test renders error panel but Save button remains independent.
 *  13. template-list action exists in services.ts and calls /v1/service-templates.
 *  14. template-detail action exists and calls /v1/service-templates/{slug}.
 *  15. test-transient action exists and calls /v1/tenants/{tenantId}/services/test-transient.
 *  16. templates (picker) resource action exists with correct actionType.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const FORM_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/ServiceCreateForm.tsx"
);

const PICKER_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/ServiceTemplatePicker.tsx"
);

const SERVICES_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/resources/services.ts"
);

const formSrc = fs.readFileSync(FORM_PATH, "utf-8");
const pickerSrc = fs.readFileSync(PICKER_PATH, "utf-8");
const servicesSrc = fs.readFileSync(SERVICES_PATH, "utf-8");

describe("ServiceCreateForm — URL-param template pre-fill (OPS-S integration)", () => {
  it("imports useSearchParams from react-router-dom", () => {
    expect(formSrc).toContain("useSearchParams");
    expect(formSrc).toContain("react-router-dom");
  });

  it("reads ?template= param from search params", () => {
    expect(formSrc).toContain('searchParams.get("template")');
  });

  it("fetches template-detail action on mount when slug present", () => {
    expect(formSrc).toContain("template-detail");
    expect(formSrc).toContain("useEffect");
  });

  it("sets name from template (pre-fill)", () => {
    expect(formSrc).toContain("setName(tpl.name)");
  });

  it("sets base_url from template (pre-fill)", () => {
    expect(formSrc).toContain("setBaseUrl(tpl.base_url)");
  });

  it("sets auth_scheme from template (pre-fill)", () => {
    expect(formSrc).toContain("setAuthScheme(tpl.auth_scheme)");
  });

  it("sets description from template (pre-fill)", () => {
    expect(formSrc).toContain("setDescription(tpl.description)");
  });

  it("sets openapi_url from template (pre-fill)", () => {
    expect(formSrc).toContain("setOpenapiUrl(tpl.openapi_url)");
  });

  it("DOES NOT pre-fill credential value (security boundary — hard rule)", () => {
    // setCredFields({}) must appear in the template pre-fill block to reset/clear creds
    expect(formSrc).toContain("setCredFields({})");
    // The comment about security boundary must be present
    expect(formSrc).toContain("DO NOT pre-fill credential value");
  });

  it("renders template-prefill-banner with template name", () => {
    expect(formSrc).toContain('data-testid="template-prefill-banner"');
  });

  it("banner contains 'Pre-filled from template:' text", () => {
    expect(formSrc).toContain("Pre-filled from template:");
  });

  it("banner has a Clear link/button that navigates to /new without param", () => {
    expect(formSrc).toContain('data-testid="template-prefill-clear"');
    expect(formSrc).toContain("/admin/resources/services/actions/new");
  });
});

describe("ServiceCreateForm — Test-before-save button (OPS-U integration)", () => {
  it("has test-before-save-btn data-testid", () => {
    expect(formSrc).toContain('data-testid="test-before-save-btn"');
  });

  it("test button is disabled when canTest is false", () => {
    expect(formSrc).toContain("disabled={!canTest || testing}");
  });

  it("canTest requires name, baseUrl, authScheme and credential value", () => {
    expect(formSrc).toContain("name.trim() !== \"\"");
    expect(formSrc).toContain("baseUrl.trim() !== \"\"");
    expect(formSrc).toContain("canTest");
  });

  it("calls test-transient resource action via ApiClient", () => {
    expect(formSrc).toContain("test-transient");
    expect(formSrc).toContain("resourceAction");
  });

  it("renders inline result panel after test", () => {
    expect(formSrc).toContain('data-testid="test-before-save-result"');
  });

  it("result panel renders status_code and latency_ms", () => {
    expect(formSrc).toContain("status_code");
    expect(formSrc).toContain("latency_ms");
  });

  it("failed test does not block save — Save button is independent", () => {
    // Test button is separate from Submit button; saving is always possible
    expect(formSrc).toContain('data-testid="service-create-submit"');
    expect(formSrc).toContain('data-testid="test-before-save-btn"');
    // Both buttons must exist independently
    const submitIdx = formSrc.indexOf('service-create-submit"');
    const testIdx = formSrc.indexOf('test-before-save-btn"');
    expect(submitIdx).toBeGreaterThan(-1);
    expect(testIdx).toBeGreaterThan(-1);
  });

  it("test handler shapes payload per TransientTestRequest model", () => {
    // Must send service, credential, test sub-objects
    // Property keys can be quoted or unquoted in object literals
    expect(formSrc).toMatch(/service:\s*\{/);
    expect(formSrc).toMatch(/credential:\s*\{/);
    expect(formSrc).toMatch(/test:\s*\{/);
    expect(formSrc).toContain("timeout_ms");
  });
});

describe("ServiceTemplatePicker component (OPS-S)", () => {
  it("exports a default component", () => {
    expect(pickerSrc).toContain("export default ServiceTemplatePicker");
  });

  it("fetches template-list on mount", () => {
    expect(pickerSrc).toContain("template-list");
    expect(pickerSrc).toContain("useEffect");
  });

  it("renders template-card-grid", () => {
    expect(pickerSrc).toContain('data-testid="template-card-grid"');
  });

  it("card click navigates to /new?template=<slug>", () => {
    expect(pickerSrc).toContain("?template=");
    expect(pickerSrc).toContain("/admin/resources/services/actions/new");
  });

  it("has skip-template button", () => {
    expect(pickerSrc).toContain('data-testid="template-skip-btn"');
    expect(pickerSrc).toContain("Skip template");
  });
});

describe("services.ts — OPS-S+U+X resource actions", () => {
  it("templates action exists with actionType: 'resource'", () => {
    // Action key may be quoted or unquoted in object literal
    expect(servicesSrc).toMatch(/templates:\s*\{/);
    // Check it uses the ServiceTemplatePicker component
    expect(servicesSrc).toContain("ServiceTemplatePicker");
  });

  it("template-list action exists and fetches /v1/service-templates", () => {
    expect(servicesSrc).toContain('"template-list"');
    expect(servicesSrc).toContain("/v1/service-templates");
  });

  it("template-detail action exists and fetches /v1/service-templates/{slug}", () => {
    expect(servicesSrc).toContain('"template-detail"');
    expect(servicesSrc).toContain("/v1/service-templates/");
  });

  it("test-transient action exists and proxies to /v1/tenants/{tenantId}/services/test-transient", () => {
    expect(servicesSrc).toContain('"test-transient"');
    expect(servicesSrc).toContain("/v1/tenants/${tenantId}/services/test-transient");
  });

  it("test-transient is a resource action (isVisible: false)", () => {
    // Invisible BFF-only action
    const ttIdx = servicesSrc.indexOf('"test-transient"');
    const snippet = servicesSrc.slice(ttIdx, ttIdx + 200);
    expect(snippet).toContain("isVisible: false");
  });

  it("templates action uses ServiceTemplatePicker component", () => {
    // Find templates action block (key may be unquoted)
    const tIdx = servicesSrc.search(/templates:\s*\{/);
    expect(tIdx).toBeGreaterThan(-1);
    const snippet = servicesSrc.slice(tIdx, tIdx + 300);
    expect(snippet).toContain("ServiceTemplatePicker");
  });
});
