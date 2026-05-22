/**
 * Unit tests for resource intro components — admin-ui-ux-uplift chunk.
 *
 * These tests verify that each intro component file exports a React component
 * as default AND that the verbatim intro paragraph text is embedded in the
 * component source. Because the vitest environment is `node` (no jsdom) we
 * validate the text content by reading the compiled source; the Playwright
 * e2e spec (`intros-and-dashboard.spec.ts`) does the real browser assertion.
 *
 * Source: admin-ui-ux-uplift acceptance criteria #4.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const SECTIONS_DIR = path.resolve(
  new URL(".", import.meta.url).pathname,
  "../../../src/components/sections"
);

function readSource(filename: string): string {
  return fs.readFileSync(path.join(SECTIONS_DIR, filename), "utf-8");
}

describe("Resource intro components — verbatim content check", () => {
  it("TenantsIntro contains first 30 chars of the tenants intro paragraph", () => {
    const src = readSource("TenantsIntro.tsx");
    expect(src).toContain("Tenants are isolated workspaces.");
  });

  it("ServicesIntro contains first 30 chars of the services intro paragraph", () => {
    const src = readSource("ServicesIntro.tsx");
    expect(src).toContain("Services are the backend APIs you");
  });

  it("CredentialsIntro contains first 30 chars of the credentials intro paragraph", () => {
    const src = readSource("CredentialsIntro.tsx");
    expect(src).toContain("Credentials are the real secrets");
  });

  it("AgentsIntro contains first 30 chars of the agents intro paragraph", () => {
    const src = readSource("AgentsIntro.tsx");
    expect(src).toContain("Agents are the AI agents");
  });

  it("PermissionsIntro contains first 30 chars of the permissions intro paragraph", () => {
    const src = readSource("PermissionsIntro.tsx");
    expect(src).toContain("Permission Grants tie an Agent");
  });

  it("ApiKeysIntro contains first 30 chars of the api keys intro paragraph", () => {
    const src = readSource("ApiKeysIntro.tsx");
    expect(src).toContain("Service API Keys");
  });

  it("AuditIntro contains first 30 chars of the audit intro paragraph", () => {
    const src = readSource("AuditIntro.tsx");
    expect(src).toContain("Audit Events are the immutable");
  });

  it("ResourceIntroList.tsx imports List from adminjs", () => {
    const src = readSource("ResourceIntroList.tsx");
    expect(src).toContain('from "adminjs"');
    expect(src).toContain("List");
  });

  it("each intro file exports a default component", () => {
    const files = [
      "TenantsIntro.tsx",
      "ServicesIntro.tsx",
      "CredentialsIntro.tsx",
      "AgentsIntro.tsx",
      "PermissionsIntro.tsx",
      "ApiKeysIntro.tsx",
      "AuditIntro.tsx",
    ];
    for (const f of files) {
      const src = readSource(f);
      expect(src, `${f} should have a default export`).toContain("export default");
    }
  });
});

describe("Dashboard.tsx — SVG and onboarding content check", () => {
  const dashboardSrc = fs.readFileSync(
    path.resolve(new URL(".", import.meta.url).pathname, "../../../src/components/Dashboard.tsx"),
    "utf-8"
  );

  it("contains SVG data-model diagram with required nodes", () => {
    expect(dashboardSrc).toContain("data-testid=\"data-model-diagram\"");
    expect(dashboardSrc).toContain("Tenant");
    expect(dashboardSrc).toContain("Service");
    expect(dashboardSrc).toContain("Credential");
    expect(dashboardSrc).toContain("Agent");
    expect(dashboardSrc).toContain("Permission");
    expect(dashboardSrc).toContain("Grant");
    expect(dashboardSrc).toContain("Service API");
    expect(dashboardSrc).toContain("Audit Events");
  });

  it("contains 6-step onboarding flow labels", () => {
    expect(dashboardSrc).toContain("Register a Service");
    expect(dashboardSrc).toContain("Attach a Credential");
    expect(dashboardSrc).toContain("Create an Agent");
    expect(dashboardSrc).toContain("Grant the Agent a Permission");
    expect(dashboardSrc).toContain("Issue a Service API Key");
    expect(dashboardSrc).toContain("Connect your LLM via MCP");
  });

  it("contains 6-step CTA links to correct resource routes", () => {
    expect(dashboardSrc).toContain("/admin/resources/services");
    expect(dashboardSrc).toContain("/admin/resources/credentials");
    expect(dashboardSrc).toContain("/admin/resources/agents");
    expect(dashboardSrc).toContain("/admin/resources/permission_grants");
    expect(dashboardSrc).toContain("/admin/resources/service_api_keys");
  });

  it("still has Quick start checklist", () => {
    expect(dashboardSrc).toContain("Quick start");
    expect(dashboardSrc).toContain("data-testid=\"dashboard-checklist-item\"");
  });

  it("still has At a glance counts", () => {
    expect(dashboardSrc).toContain("At a glance");
    expect(dashboardSrc).toContain("data-testid=\"dashboard-count\"");
  });

  it("has get-started-section testid", () => {
    expect(dashboardSrc).toContain("data-testid=\"get-started-section\"");
  });

  it("has diagram-section testid", () => {
    expect(dashboardSrc).toContain("data-testid=\"diagram-section\"");
  });
});
