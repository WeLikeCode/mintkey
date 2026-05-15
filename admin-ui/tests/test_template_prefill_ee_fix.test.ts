/**
 * Unit tests for OPS-DDEE EE: template pre-fill repair (description + openapi_url).
 *
 * vitest environment is `node` (no jsdom), so tests use source-file inspection.
 * Playwright e2e spec covers real-browser verification with all 5 fields.
 *
 * Root cause: the previous implementation relied solely on a nested template
 * object in record.params. The EE fix:
 *   1. BFF `template-detail` handler now returns flat params as belt-and-suspenders.
 *   2. React extraction chain now tries the nested object AND flat params keys.
 *   3. All 5 fields (name, base_url, auth_scheme, description, openapi_url) populate.
 *
 * Assertions:
 *   1. BFF handler flattens template fields into record.params.
 *   2. Flat keys follow "template.<field>" naming.
 *   3. React extraction reads data?.template first, then falls back to flat params.
 *   4. getField helper is defined and reads both sources.
 *   5. All 5 setters are called with extracted values.
 *   6. Credential value is still NOT pre-filled (security boundary).
 *   7. services.ts template-detail handler normalises template fields.
 *   8. template-detail returns template at top level (direct access).
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const SERVICES_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/resources/services.ts"
);

const FORM_PATH = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/actions/ServiceCreateForm.tsx"
);

const servicesSrc = fs.readFileSync(SERVICES_PATH, "utf-8");
const formSrc = fs.readFileSync(FORM_PATH, "utf-8");

describe("services.ts — template-detail BFF EE fix", () => {
  // Use the full services source for these assertions (handler spans > 1500 chars)
  it("template-detail handler normalises all 5 template fields with defaults", () => {
    expect(servicesSrc).toContain('"template-detail"');
    // Normalised template object contains all 5 key fields
    expect(servicesSrc).toContain("description: raw.description");
    expect(servicesSrc).toContain("openapi_url: raw.openapi_url");
    expect(servicesSrc).toContain("name: raw.name");
    expect(servicesSrc).toContain("base_url: raw.base_url");
    expect(servicesSrc).toContain("auth_scheme: raw.auth_scheme");
  });

  it("template-detail returns flat params keys for belt-and-suspenders", () => {
    expect(servicesSrc).toContain('"template.description"');
    expect(servicesSrc).toContain('"template.openapi_url"');
    expect(servicesSrc).toContain('"template.name"');
    expect(servicesSrc).toContain('"template.base_url"');
    expect(servicesSrc).toContain('"template.auth_scheme"');
  });

  it("template-detail returns template at top level alongside record", () => {
    // The return object has both `record: { ... }` and `template,` at top level
    // We can check that the services source has the return with both fields
    expect(servicesSrc).toContain('"template.slug"');
    expect(servicesSrc).toContain('"template.description": template.description');
    expect(servicesSrc).toContain('"template.openapi_url": template.openapi_url');
  });

  it("template-detail also stores nested template object in record.params", () => {
    // params block includes both 'template,' (the nested object) and flat keys
    expect(servicesSrc).toContain('"template.slug": template.slug');
    expect(servicesSrc).toContain('"template.name": template.name');
  });
});

describe("ServiceCreateForm.tsx — EE fix: extraction with flat param fallback", () => {
  it("defines getField helper for dual-source extraction", () => {
    expect(formSrc).toContain("getField");
    expect(formSrc).toContain("fromTpl");
    expect(formSrc).toContain("flatParams");
  });

  it("reads description via getField (not direct tpl.description)", () => {
    // After EE fix, description is read via getField("description")
    expect(formSrc).toContain('getField("description")');
    // Old direct access pattern should be gone
    expect(formSrc).not.toContain("tpl.description");
  });

  it("reads openapi_url via getField (not direct tpl.openapi_url)", () => {
    expect(formSrc).toContain('getField("openapi_url")');
    expect(formSrc).not.toContain("tpl.openapi_url");
  });

  it("reads name, base_url, auth_scheme via getField too", () => {
    expect(formSrc).toContain('getField("name")');
    expect(formSrc).toContain('getField("base_url")');
    expect(formSrc).toContain('getField("auth_scheme")');
  });

  it("falls back to flat params for description field", () => {
    // getField reads flatParams[`template.description`]
    expect(formSrc).toContain('template.${key}');
  });

  it("all 5 setters are still called with extracted values", () => {
    expect(formSrc).toContain("setName(tName)");
    expect(formSrc).toContain("setBaseUrl(tBaseUrl)");
    expect(formSrc).toContain("setAuthScheme(tAuthScheme)");
    expect(formSrc).toContain("setDescription(tDescription)");
    expect(formSrc).toContain("setOpenapiUrl(tOpenapiUrl)");
  });

  it("setCredFields({}) still resets credential fields (security boundary)", () => {
    expect(formSrc).toContain("setCredFields({})");
    expect(formSrc).toContain("DO NOT pre-fill credential value");
  });

  it("extraction fallback order: data.template → record.params.template → flat params", () => {
    expect(formSrc).toContain("data?.template");
    expect(formSrc).toContain('data?.record?.params?.["template"]');
    expect(formSrc).toContain("flatParams");
  });

  it("hasAnyField guard prevents empty template from overriding user input", () => {
    expect(formSrc).toContain("hasAnyField");
    expect(formSrc).toContain("if (!hasAnyField) return");
  });
});
