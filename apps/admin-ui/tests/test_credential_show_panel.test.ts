/**
 * Unit tests for CredentialShowPanel — OPS-Y.
 *
 * Validates that the component source contains all four required elements:
 *   1. Header paragraph with "envelope-encrypted in the Vault Adapter" phrase.
 *   2. Service link pointing to the services show route.
 *   3. Audit history link with filters.target_id query param.
 *   4. Backlog note referencing TODO-last-used.
 *
 * Because vitest runs in `node` environment (no jsdom) these tests validate
 * source text content — the Playwright e2e spec does the real browser assertion.
 *
 * Source: OPS-Y spec; ADMIN_UI_SPEC.md §2.4.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const SECTIONS_DIR = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../src/components/sections"
);

function readSource(filename: string): string {
  return fs.readFileSync(path.join(SECTIONS_DIR, filename), "utf-8");
}

const src = readSource("CredentialShowPanel.tsx");

describe("CredentialShowPanel — source content", () => {
  it("exports a default React component", () => {
    expect(src).toContain("export default");
    expect(src).toContain("CredentialShowPanel");
  });

  it("header paragraph mentions envelope-encrypted in the Vault Adapter", () => {
    expect(src).toContain("envelope-encrypted in the Vault Adapter");
  });

  it("header paragraph mentions Egress Proxy injecting credential", () => {
    expect(src).toContain("Egress Proxy");
  });

  it("header paragraph says Agents never see the value", () => {
    expect(src).toContain("Agents never see the value");
  });

  it("service link points to /admin/resources/services/records/", () => {
    expect(src).toContain("/admin/resources/services/records/");
  });

  it("audit history link uses filters.target_id query param", () => {
    expect(src).toContain("filters.target_id=");
  });

  it("audit history link points to audit_events resource", () => {
    expect(src).toContain("/admin/resources/audit_events");
  });

  it("backlog note references TODO-last-used", () => {
    expect(src).toContain("TODO-last-used");
  });

  it("backlog note mentions last-used timestamp", () => {
    expect(src).toContain("Last-used timestamp not yet tracked");
  });

  it("has testid for the panel container", () => {
    expect(src).toContain("data-testid=\"credential-show-panel\"");
  });

  it("has testid for the intro paragraph", () => {
    expect(src).toContain("data-testid=\"credential-show-panel-intro\"");
  });

  it("has testid for the service link", () => {
    expect(src).toContain("data-testid=\"credential-show-panel-service-link\"");
  });

  it("has testid for the audit history link", () => {
    expect(src).toContain("data-testid=\"credential-show-panel-audit-link\"");
  });

  it("has testid for the backlog note", () => {
    expect(src).toContain("data-testid=\"credential-show-panel-backlog-note\"");
  });
});

describe("credentials.ts — _credentialShowPanel wiring", () => {
  const credSrc = fs.readFileSync(
    path.resolve(new URL(".", import.meta.url).pathname, "../src/resources/credentials.ts"),
    "utf-8"
  );

  it("declares _credentialShowPanel as a virtual property in RestResource", () => {
    expect(credSrc).toContain("\"_credentialShowPanel\"");
  });

  it("places _credentialShowPanel first in showProperties", () => {
    const match = credSrc.match(/showProperties:\s*\[([^\]]+)\]/);
    expect(match, "showProperties must be defined").not.toBeNull();
    const props = match![1].trim();
    expect(props).toMatch(/^["']_credentialShowPanel["']/);
  });

  it("_credentialShowPanel is only visible on show (not list/edit/new/filter)", () => {
    expect(credSrc).toContain("show: true, list: false, edit: false, new: false, filter: false");
  });

  it("_credentialShowPanel component is set to Components.CredentialShowPanel", () => {
    expect(credSrc).toContain("Components.CredentialShowPanel");
  });

  it("name property label is renamed to Service", () => {
    // The name property should have label: "Service"
    expect(credSrc).toContain('label: "Service"');
  });
});
