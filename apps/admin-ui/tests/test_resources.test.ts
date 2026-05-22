/**
 * AdminJS resource configuration tests — T-1.2.3, T-1.3.4, T-1.4.3,
 * T-1.7.4, T-1.8.4, T-1.9.4, T-1.12.4.
 *
 * Tests:
 * - Each resource is exported with the correct resource key.
 * - Audit resource has all write actions hidden (append-only).
 * - Credentials resource has the rotate action.
 * - Agents resource has the revoke action.
 * - Tenants resource has no delete action.
 *
 * Source: T-1.2.3; T-1.3.4; T-1.4.3; T-1.7.4; T-1.8.4; T-1.9.4; T-1.12.4;
 *         ADR-0013; ADR-0014.5.
 */

import { describe, it, expect } from "vitest";
import { ServicesResource } from "../src/resources/services.js";
import { CredentialsResource } from "../src/resources/credentials.js";
import { AgentsResource } from "../src/resources/agents.js";
import { PermissionsResource } from "../src/resources/permissions.js";
import { AuditResource } from "../src/resources/audit.js";
import { TenantsResource } from "../src/resources/tenants.js";

describe("ServicesResource", () => {
  it("has resource key", () => {
    expect(ServicesResource.resource).toBe("services");
  });

  it("has testService action", () => {
    const actions = ServicesResource.options?.actions ?? {};
    expect("testService" in actions).toBe(true);
  });

  it("exposes new, edit, delete actions", () => {
    const actions = ServicesResource.options?.actions ?? {};
    expect("new" in actions).toBe(true);
    expect("edit" in actions).toBe(true);
    expect("delete" in actions).toBe(true);
  });
});

describe("CredentialsResource — T-1.3.4 + T-1.8.4", () => {
  it("has resource key", () => {
    expect(CredentialsResource.resource).toBe("credentials");
  });

  it("has rotateCredential action (T-1.8.4)", () => {
    const actions = CredentialsResource.options?.actions ?? {};
    expect("rotateCredential" in actions).toBe(true);
  });

  it("edit action is not visible (credentials cannot be edited directly)", () => {
    const actions = CredentialsResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).edit?.isVisible).toBe(false);
  });

  it("delete action is not visible (credentials cannot be deleted via UI)", () => {
    const actions = CredentialsResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).delete?.isVisible).toBe(false);
  });
});

describe("AgentsResource — T-1.4.3 + T-1.9.4", () => {
  it("has resource key", () => {
    expect(AgentsResource.resource).toBe("agents");
  });

  it("has revokeAgent action (T-1.9.4)", () => {
    const actions = AgentsResource.options?.actions ?? {};
    expect("revokeAgent" in actions).toBe(true);
  });

  it("revoke action is record-level", () => {
    const actions = AgentsResource.options?.actions ?? {};
    expect((actions as Record<string, { actionType?: string }>).revokeAgent?.actionType).toBe("record");
  });
});

describe("PermissionsResource — T-1.4.3", () => {
  it("has resource key", () => {
    expect(PermissionsResource.resource).toBe("permission_grants");
  });

  it("edit action is not visible", () => {
    const actions = PermissionsResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).edit?.isVisible).toBe(false);
  });
});

describe("AuditResource — T-1.7.4 (read-only)", () => {
  it("has resource key", () => {
    expect(AuditResource.resource).toBe("audit_events");
  });

  it("new action is not visible (append-only)", () => {
    const actions = AuditResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).new?.isVisible).toBe(false);
  });

  it("edit action is not visible (append-only)", () => {
    const actions = AuditResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).edit?.isVisible).toBe(false);
  });

  it("delete action is not visible (append-only)", () => {
    const actions = AuditResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).delete?.isVisible).toBe(false);
  });

  it("bulkDelete action is not visible", () => {
    const actions = AuditResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).bulkDelete?.isVisible).toBe(false);
  });
});

describe("TenantsResource — T-1.12.4 (PlatformAdmin)", () => {
  it("has resource key", () => {
    expect(TenantsResource.resource).toBe("tenants");
  });

  it("delete action is not visible (tenants cannot be deleted via UI)", () => {
    const actions = TenantsResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).delete?.isVisible).toBe(false);
  });

  it("new action is visible", () => {
    const actions = TenantsResource.options?.actions ?? {};
    expect("new" in actions).toBe(true);
  });
});
