/**
 * CHUNK 2: Auth scheme dropdown + conditional credential fields.
 *
 * Tests verify:
 * - AUTH_SCHEMES list has all 8 options
 * - getCredentialFields returns the correct fields for each scheme
 * - Secret fields are identified correctly (type=password)
 * - buildCredentialPayload constructs the right request body
 *
 * Source: ADMIN_UI_SPEC.md §1.1; T-1.3.4; ADR-0014.4; ADR-0014.5.
 */

import { describe, it, expect } from "vitest";
import {
  AUTH_SCHEMES,
  getCredentialFields,
  buildCredentialPayload,
  type CredentialField,
} from "../src/lib/auth-scheme.js";

describe("AUTH_SCHEMES", () => {
  it("contains all 8 required schemes", () => {
    const values = AUTH_SCHEMES.map((s) => s.value);
    expect(values).toContain("none");
    expect(values).toContain("api_key_header");
    expect(values).toContain("api_key_query");
    expect(values).toContain("bearer_token");
    expect(values).toContain("basic_auth");
    expect(values).toContain("oauth2_client_credentials");
    expect(values).toContain("oidc_client_secret");
    expect(values).toContain("mtls");
    expect(values).length(8);
  });

  it("each scheme has a value and label", () => {
    for (const s of AUTH_SCHEMES) {
      expect(typeof s.value).toBe("string");
      expect(typeof s.label).toBe("string");
      expect(s.label.length).toBeGreaterThan(0);
    }
  });
});

describe("getCredentialFields", () => {
  it("none returns empty fields array (no credential needed)", () => {
    const fields = getCredentialFields("none");
    expect(fields).toEqual([]);
  });

  it("api_key_header returns header_name + value (password)", () => {
    const fields = getCredentialFields("api_key_header");
    const names = fields.map((f) => f.name);
    expect(names).toContain("header_name");
    expect(names).toContain("value");
    const valueField = fields.find((f) => f.name === "value")!;
    expect(valueField.secret).toBe(true);
  });

  it("api_key_query returns param_name + value (password)", () => {
    const fields = getCredentialFields("api_key_query");
    const names = fields.map((f) => f.name);
    expect(names).toContain("param_name");
    expect(names).toContain("value");
    const valueField = fields.find((f) => f.name === "value")!;
    expect(valueField.secret).toBe(true);
  });

  it("bearer_token returns value only (password)", () => {
    const fields = getCredentialFields("bearer_token");
    expect(fields).toHaveLength(1);
    expect(fields[0].name).toBe("value");
    expect(fields[0].secret).toBe(true);
  });

  it("basic_auth returns username + password", () => {
    const fields = getCredentialFields("basic_auth");
    const names = fields.map((f) => f.name);
    expect(names).toContain("username");
    expect(names).toContain("password");
    const pw = fields.find((f) => f.name === "password")!;
    expect(pw.secret).toBe(true);
  });

  it("oauth2_client_credentials returns token_url, client_id, client_secret, scopes, audience", () => {
    const fields = getCredentialFields("oauth2_client_credentials");
    const names = fields.map((f) => f.name);
    expect(names).toContain("token_url");
    expect(names).toContain("client_id");
    expect(names).toContain("client_secret");
    expect(names).toContain("scopes");
    const cs = fields.find((f) => f.name === "client_secret")!;
    expect(cs.secret).toBe(true);
  });

  it("oidc_client_secret returns issuer, client_id, client_secret, scopes", () => {
    const fields = getCredentialFields("oidc_client_secret");
    const names = fields.map((f) => f.name);
    expect(names).toContain("issuer");
    expect(names).toContain("client_id");
    expect(names).toContain("client_secret");
    const cs = fields.find((f) => f.name === "client_secret")!;
    expect(cs.secret).toBe(true);
  });

  it("mtls returns client_cert_pem (textarea) and client_key_pem (textarea, secret)", () => {
    const fields = getCredentialFields("mtls");
    const names = fields.map((f) => f.name);
    expect(names).toContain("client_cert_pem");
    expect(names).toContain("client_key_pem");
    const keyField = fields.find((f) => f.name === "client_key_pem")!;
    expect(keyField.secret).toBe(true);
    expect(keyField.type).toBe("textarea");
  });

  it("unknown scheme returns empty fields (safe default)", () => {
    const fields = getCredentialFields("unknown_scheme");
    expect(fields).toEqual([]);
  });
});

describe("buildCredentialPayload", () => {
  it("api_key_header: builds {auth_scheme, header_name, value}", () => {
    const payload = buildCredentialPayload("api_key_header", {
      header_name: "X-API-Key",
      value: "secret123",
    });
    expect(payload.auth_scheme).toBe("api_key_header");
    expect(payload.header_name).toBe("X-API-Key");
    expect(payload.value).toBe("secret123");
  });

  it("basic_auth: builds {auth_scheme, username, password}", () => {
    const payload = buildCredentialPayload("basic_auth", {
      username: "user",
      password: "pass",
    });
    expect(payload.auth_scheme).toBe("basic_auth");
    expect(payload.username).toBe("user");
    expect(payload.password).toBe("pass");
  });

  it("none: builds {auth_scheme: none} with no extra fields", () => {
    const payload = buildCredentialPayload("none", {});
    expect(payload).toEqual({ auth_scheme: "none" });
  });
});
