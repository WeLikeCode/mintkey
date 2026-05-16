/**
 * CHUNK 0: P0 boot tests — AdminJS serves /admin/login, resources registered.
 *
 * Tests verify:
 * - RestResource instances are constructable without error
 * - auth options have the authenticate function (break-glass helper)
 * - adminJSAuthOptions.cookieName is set (session cookie configured)
 * - All 7 resources export a .resource id string
 *
 * SSO-C: authenticate() is now the break-glass internal-login helper (not the
 * primary login path — that's handled via /auth/start → admin-api → Keycloak).
 *
 * Source: T-1.1.4; T-1.2.3; ADR-0013; ADR-0014.5; SSO-C.
 */

import { describe, it, expect } from "vitest";
import { adminJSAuthOptions } from "../src/auth.js";
import { ServicesResource } from "../src/resources/services.js";
import { CredentialsResource } from "../src/resources/credentials.js";
import { AgentsResource } from "../src/resources/agents.js";
import { PermissionsResource } from "../src/resources/permissions.js";
import { AuditResource } from "../src/resources/audit.js";
import { TenantsResource } from "../src/resources/tenants.js";
import { RestResource } from "../src/lib/rest-resource.js";

describe("P0-1: AdminJS resources are registered", () => {
  it("ServicesResource exports a string resource id", () => {
    expect(typeof ServicesResource.resource).toBe("string");
    expect(ServicesResource.resource).toBe("services");
  });

  it("CredentialsResource exports a string resource id", () => {
    expect(typeof CredentialsResource.resource).toBe("string");
    expect(CredentialsResource.resource).toBe("credentials");
  });

  it("AgentsResource exports a string resource id", () => {
    expect(typeof AgentsResource.resource).toBe("string");
    expect(AgentsResource.resource).toBe("agents");
  });

  it("PermissionsResource exports a string resource id", () => {
    expect(typeof PermissionsResource.resource).toBe("string");
    expect(PermissionsResource.resource).toBe("permission_grants");
  });

  it("AuditResource exports a string resource id", () => {
    expect(typeof AuditResource.resource).toBe("string");
    expect(AuditResource.resource).toBe("audit_events");
  });

  it("TenantsResource exports a string resource id", () => {
    expect(typeof TenantsResource.resource).toBe("string");
    expect(TenantsResource.resource).toBe("tenants");
  });

  it("All resources have options with navigation", () => {
    for (const r of [ServicesResource, CredentialsResource, AgentsResource, PermissionsResource, AuditResource, TenantsResource]) {
      expect(r.options).toBeTruthy();
      expect(r.options.navigation).toBeTruthy();
    }
  });
});

describe("P0-2: Session is configured", () => {
  it("adminJSAuthOptions has cookieName set", () => {
    expect(adminJSAuthOptions.cookieName).toBe("mintkey_session");
  });

  it("adminJSAuthOptions has authenticate function", () => {
    expect(typeof adminJSAuthOptions.authenticate).toBe("function");
  });

  it("adminJSAuthOptions has cookiePassword set", () => {
    expect(typeof adminJSAuthOptions.cookiePassword).toBe("string");
    expect(adminJSAuthOptions.cookiePassword.length).toBeGreaterThan(0);
  });
});

describe("P0-3: RestResource is constructable without DB connection", () => {
  it("constructs a RestResource and returns correct id", () => {
    const r = new RestResource({
      id: "test_resource",
      name: "Test",
      listPath: "/v1/tenants/{tenantId}/test",
      listKey: "items",
      properties: [
        { path: "id", type: "string", isId: true },
        { path: "name", type: "string" },
      ],
    });
    expect(r.id()).toBe("test_resource");
    expect(r.name()).toBe("Test");
    expect(r.databaseName()).toBe("mintkey-api");
    expect(r.properties().length).toBe(2);
  });

  it("properties returns BaseProperty instances with correct types", () => {
    const r = new RestResource({
      id: "t", name: "T",
      listPath: "/v1/test",
      listKey: "items",
      properties: [
        { path: "id", type: "uuid", isId: true },
        { path: "count", type: "number" },
      ],
    });
    const props = r.properties();
    expect(props[0].type()).toBe("uuid");
    expect(props[0].isId()).toBe(true);
    expect(props[1].type()).toBe("number");
  });
});
