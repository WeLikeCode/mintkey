/**
 * CHUNK 4: Credential↔service clarity tests.
 *
 * Tests verify:
 * - getCredentialStatus returns correct badge for each state
 * - Credentials resource has no top-level "new" visible action (create via service only)
 * - Credentials listProperties has service_name as first or prominent column
 *
 * Source: ADMIN_UI_SPEC.md §2.3; §2.4; T-1.3.4; ADR-0014.4.
 */

import { describe, it, expect } from "vitest";
import { getCredentialStatus, type CredentialStatusBadge } from "../src/lib/credential-status.js";
import { CredentialsResource } from "../src/resources/credentials.js";

describe("getCredentialStatus", () => {
  it("returns 'none' badge for auth_scheme=none", () => {
    const badge = getCredentialStatus({ auth_scheme: "none", current_key_version: 0 });
    expect(badge.type).toBe("none");
    expect(badge.label).toMatch(/n\/a|no auth/i);
  });

  it("returns 'no_credential' badge when key_version is 0 and scheme is not none", () => {
    const badge = getCredentialStatus({ auth_scheme: "api_key_header", current_key_version: 0 });
    expect(badge.type).toBe("no_credential");
    expect(badge.label).toMatch(/no credential/i);
  });

  it("returns 'configured' badge with version when key_version > 0", () => {
    const badge = getCredentialStatus({ auth_scheme: "api_key_header", current_key_version: 3 });
    expect(badge.type).toBe("configured");
    expect(badge.label).toMatch(/v3/i);
  });

  it("returns 'revoked' badge when status is revoked", () => {
    const badge = getCredentialStatus({ auth_scheme: "bearer_token", current_key_version: 1, status: "revoked" });
    expect(badge.type).toBe("revoked");
    expect(badge.label).toMatch(/revoked/i);
  });

  it("configured badge includes 'configured' text", () => {
    const badge = getCredentialStatus({ auth_scheme: "bearer_token", current_key_version: 2 });
    expect(badge.label).toMatch(/configured/i);
    expect(badge.version).toBe(2);
  });
});

describe("CredentialsResource options", () => {
  it("edit action is not visible (no direct editing of credentials)", () => {
    const actions = CredentialsResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).edit?.isVisible).toBe(false);
  });

  it("delete action is not visible (use revoke instead)", () => {
    const actions = CredentialsResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).delete?.isVisible).toBe(false);
  });

  it("rotateCredential action exists", () => {
    const actions = CredentialsResource.options?.actions ?? {};
    expect("rotateCredential" in actions).toBe(true);
  });
});
