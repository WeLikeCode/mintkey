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
  it("contains all 12 required schemes", () => {
    const values = AUTH_SCHEMES.map((s) => s.value);
    expect(values).toContain("none");
    expect(values).toContain("api_key_header");
    expect(values).toContain("api_key_query");
    expect(values).toContain("bearer_token");
    expect(values).toContain("basic_auth");
    expect(values).toContain("oauth2_client_credentials");
    expect(values).toContain("oauth2_password_grant");
    expect(values).toContain("oidc_client_secret");
    expect(values).toContain("mtls");
    expect(values).toContain("apple_jwt");
    expect(values).toContain("google_service_account");
    expect(values).toContain("ssh_private_key");
    expect(values).toContain("ssh_ca");
    expect(values).length(13);
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

  it("oauth2_password_grant returns token_url, credential_fields kv-editor, token_response_path, exchange_timeout_seconds", () => {
    const fields = getCredentialFields("oauth2_password_grant");
    const names = fields.map((f) => f.name);
    expect(names).toContain("token_url");
    expect(names).toContain("credential_fields");
    expect(names).toContain("token_response_path");
    expect(names).toContain("exchange_timeout_seconds");
    const kvField = fields.find((f) => f.name === "credential_fields")!;
    expect(kvField.type).toBe("kv-editor");
    expect(kvField.secret).toBe(false);
    const timeoutField = fields.find((f) => f.name === "exchange_timeout_seconds")!;
    expect(timeoutField.type).toBe("number");
    expect(timeoutField.defaultValue).toBe("10");
    expect(timeoutField.min).toBe(1);
    expect(timeoutField.max).toBe(120);
  });

  it("apple_jwt returns p8_key_pem (textarea, secret), key_id (text), issuer_id (text)", () => {
    const fields = getCredentialFields("apple_jwt");
    const names = fields.map((f) => f.name);
    expect(names).toContain("p8_key_pem");
    expect(names).toContain("key_id");
    expect(names).toContain("issuer_id");
    expect(fields).toHaveLength(3);
    const p8Field = fields.find((f) => f.name === "p8_key_pem")!;
    expect(p8Field.type).toBe("textarea");
    expect(p8Field.secret).toBe(true);
    expect(p8Field.required).toBe(true);
    const keyIdField = fields.find((f) => f.name === "key_id")!;
    expect(keyIdField.type).toBe("text");
    expect(keyIdField.required).toBe(true);
    const issuerField = fields.find((f) => f.name === "issuer_id")!;
    expect(issuerField.type).toBe("text");
    expect(issuerField.required).toBe(true);
  });

  it("google_service_account returns service_account_json (textarea, secret) + scope (text, not secret)", () => {
    const fields = getCredentialFields("google_service_account");
    expect(fields).toHaveLength(2);
    const names = fields.map((f) => f.name);
    expect(names).toContain("service_account_json");
    expect(names).toContain("scope");
    const jsonField = fields.find((f) => f.name === "service_account_json")!;
    expect(jsonField.type).toBe("textarea");
    expect(jsonField.secret).toBe(true);
    expect(jsonField.required).toBe(true);
    const scopeField = fields.find((f) => f.name === "scope")!;
    expect(scopeField.type).toBe("text");
    expect(scopeField.secret).toBe(false);
    expect(scopeField.required).toBe(true);
    expect(scopeField.defaultValue).toBe("https://www.googleapis.com/auth/androidpublisher");
  });

  it("ssh_private_key returns private_key_pem (textarea, secret), target_address (text), ssh_user (text)", () => {
    const fields = getCredentialFields("ssh_private_key");
    expect(fields).toHaveLength(3);
    const names = fields.map((f) => f.name);
    expect(names).toContain("private_key_pem");
    expect(names).toContain("target_address");
    expect(names).toContain("ssh_user");
    const keyField = fields.find((f) => f.name === "private_key_pem")!;
    expect(keyField.type).toBe("textarea");
    expect(keyField.secret).toBe(true);
    expect(keyField.required).toBe(true);
    const addrField = fields.find((f) => f.name === "target_address")!;
    expect(addrField.type).toBe("text");
    expect(addrField.secret).toBe(false);
    expect(addrField.required).toBe(true);
    const userField = fields.find((f) => f.name === "ssh_user")!;
    expect(userField.type).toBe("text");
    expect(userField.secret).toBe(false);
    expect(userField.required).toBe(true);
  });

  it("ssh_ca returns ca_private_key_pem (textarea, secret), ca_principal_prefix (text, required)", () => {
    const fields = getCredentialFields("ssh_ca");
    expect(fields).toHaveLength(2);
    const names = fields.map((f) => f.name);
    expect(names).toContain("ca_private_key_pem");
    expect(names).toContain("ca_principal_prefix");
    const caKeyField = fields.find((f) => f.name === "ca_private_key_pem")!;
    expect(caKeyField.type).toBe("textarea");
    expect(caKeyField.secret).toBe(true);
    expect(caKeyField.required).toBe(true);
    const prefixField = fields.find((f) => f.name === "ca_principal_prefix")!;
    expect(prefixField.type).toBe("text");
    expect(prefixField.secret).toBe(false);
    expect(prefixField.required).toBe(true);
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

  it("apple_jwt: assembles nested value JSON with scheme, p8_key_pem, key_id, issuer_id", () => {
    const payload = buildCredentialPayload("apple_jwt", {
      p8_key_pem: "-----BEGIN PRIVATE KEY-----\nMIGH...\n-----END PRIVATE KEY-----",
      key_id: "TNRVKBLCWWTH",
      issuer_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    });
    expect(payload.auth_scheme).toBe("apple_jwt");
    const valueObj = JSON.parse(payload.value);
    expect(valueObj.scheme).toBe("apple_jwt");
    expect(valueObj.p8_key_pem).toBe("-----BEGIN PRIVATE KEY-----\nMIGH...\n-----END PRIVATE KEY-----");
    expect(valueObj.key_id).toBe("TNRVKBLCWWTH");
    expect(valueObj.issuer_id).toBe("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
  });

  it("google_service_account: value is JSON string with exactly 3 keys", () => {
    const saJson = '{"type":"service_account","project_id":"my-proj"}';
    const payload = buildCredentialPayload("google_service_account", {
      service_account_json: saJson,
      scope: "https://example/scope",
    });
    expect(payload.auth_scheme).toBe("google_service_account");
    expect(typeof payload.value).toBe("string");
    const parsed = JSON.parse(payload.value);
    expect(parsed.scheme).toBe("google_service_account");
    expect(parsed.service_account_json).toBe(saJson);
    expect(parsed.scope).toBe("https://example/scope");
    // Exactly 3 keys — no extras
    expect(Object.keys(parsed)).toHaveLength(3);
  });

  it("google_service_account: re-parsing payload.value returns scheme, service_account_json, scope only", () => {
    const payload = buildCredentialPayload("google_service_account", {
      service_account_json: '{"type":"service_account"}',
      scope: "https://www.googleapis.com/auth/androidpublisher",
    });
    const parsed = JSON.parse(payload.value);
    expect(Object.keys(parsed).sort()).toEqual(["scheme", "scope", "service_account_json"].sort());
  });

  it("ssh_private_key: value is JSON string with exactly 4 keys (scheme, private_key_pem, target_address, ssh_user)", () => {
    const payload = buildCredentialPayload("ssh_private_key", {
      private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNza...\n-----END OPENSSH PRIVATE KEY-----",
      target_address: "host:22",
      ssh_user: "alice",
    });
    expect(payload.auth_scheme).toBe("ssh_private_key");
    expect(typeof payload.value).toBe("string");
    const parsed = JSON.parse(payload.value);
    expect(parsed.scheme).toBe("ssh_private_key");
    expect(parsed.private_key_pem).toBe("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNza...\n-----END OPENSSH PRIVATE KEY-----");
    expect(parsed.target_address).toBe("host:22");
    expect(parsed.ssh_user).toBe("alice");
    expect(Object.keys(parsed)).toHaveLength(4);
  });

  it("ssh_private_key: round-trip JSON.parse returns expected object shape", () => {
    const payload = buildCredentialPayload("ssh_private_key", {
      private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----",
      target_address: "10.0.0.5:22",
      ssh_user: "ubuntu",
    });
    const parsed = JSON.parse(payload.value);
    expect(Object.keys(parsed).sort()).toEqual(["private_key_pem", "scheme", "ssh_user", "target_address"].sort());
    expect(parsed.target_address).toBe("10.0.0.5:22");
    expect(parsed.ssh_user).toBe("ubuntu");
  });

  it("ssh_ca: value is JSON string with exactly 3 keys (scheme, ca_private_key_pem, ca_principal_prefix)", () => {
    const payload = buildCredentialPayload("ssh_ca", {
      ca_private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nca_key\n-----END OPENSSH PRIVATE KEY-----",
      ca_principal_prefix: "agent-",
    });
    expect(payload.auth_scheme).toBe("ssh_ca");
    expect(typeof payload.value).toBe("string");
    const parsed = JSON.parse(payload.value);
    expect(parsed.scheme).toBe("ssh_ca");
    expect(parsed.ca_private_key_pem).toBe("-----BEGIN OPENSSH PRIVATE KEY-----\nca_key\n-----END OPENSSH PRIVATE KEY-----");
    expect(parsed.ca_principal_prefix).toBe("agent-");
    expect(Object.keys(parsed)).toHaveLength(3);
  });

  it("ssh_ca: round-trip JSON.parse returns expected object shape", () => {
    const payload = buildCredentialPayload("ssh_ca", {
      ca_private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nca\n-----END OPENSSH PRIVATE KEY-----",
      ca_principal_prefix: "svc-",
    });
    const parsed = JSON.parse(payload.value);
    expect(Object.keys(parsed).sort()).toEqual(["ca_principal_prefix", "ca_private_key_pem", "scheme"].sort());
    expect(parsed.ca_principal_prefix).toBe("svc-");
  });

  it("oauth2_password_grant: assembles nested value JSON with correct contract shape", () => {
    const payload = buildCredentialPayload("oauth2_password_grant", {
      token_url: "https://dashboard-api-ps-stag.azurewebsites.net/api/v1/Token",
      credential_fields_json: JSON.stringify({ userName: "vrusu", password: "Asd123!" }),
      token_response_path: "$.data.token",
      exchange_timeout_seconds: "30",
    });
    expect(payload.auth_scheme).toBe("oauth2_password_grant");
    expect(payload.token_url).toBe("https://dashboard-api-ps-stag.azurewebsites.net/api/v1/Token");
    const valueObj = JSON.parse(payload.value);
    expect(valueObj.token_url).toBe("https://dashboard-api-ps-stag.azurewebsites.net/api/v1/Token");
    expect(valueObj.credential_fields).toEqual({ userName: "vrusu", password: "Asd123!" });
    expect(valueObj.token_response_path).toBe("$.data.token");
    expect(valueObj.exchange_timeout_seconds).toBe(30);
  });
});
